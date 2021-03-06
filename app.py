# -*- encoding: utf-8 -*-
from datetime import datetime

from esipy import App
from esipy import EsiClient
from esipy import EsiSecurity
from esipy.exceptions import APIException

from flask import Flask
from flask import redirect
from flask import render_template
from flask import request
from flask import session
from flask import url_for
from flask import jsonify

from flask_login import LoginManager
from flask_login import UserMixin
from flask_login import current_user
from flask_login import login_required
from flask_login import login_user
from flask_login import logout_user

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.schema import PrimaryKeyConstraint
from sqlalchemy import func

import config
import hashlib
import hmac
import logging
import random
import time

# logger stuff
logger = logging.getLogger(__name__)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
console.setFormatter(formatter)
logger.addHandler(console)

# init app and load conf
app = Flask(__name__)
app.config.from_object(config)

# init db
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# init flask login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


# -----------------------------------------------------------------------
# Database models
# -----------------------------------------------------------------------
class User(db.Model, UserMixin):
    # our ID is the character ID from EVE API
    character_id = db.Column(
        db.BigInteger,
        primary_key=True,
        autoincrement=False
    )
    character_owner_hash = db.Column(db.String(255))
    character_name = db.Column(db.String(200))

    # SSO Token stuff
    access_token = db.Column(db.String(100))
    access_token_expires = db.Column(db.DateTime())
    refresh_token = db.Column(db.String(100))
    latest_seen = db.Column(db.DateTime())

    def get_id(self):
        """ Required for flask-login """
        return self.character_id

    def get_sso_data(self):
        """ Little "helper" function to get formated data for esipy security
        """
        return {
            'access_token': self.access_token,
            'refresh_token': self.refresh_token,
            'expires_in': (
                self.access_token_expires - datetime.utcnow()
            ).total_seconds()
        }

    def update_token(self, token_response):
        """ helper function to update token data from SSO response """
        self.access_token = token_response['access_token']
        self.access_token_expires = datetime.fromtimestamp(
            time.time() + token_response['expires_in'],
        )
        if 'refresh_token' in token_response:
            self.refresh_token = token_response['refresh_token']

class MiningData(db.Model):
    character_id = db.Column(db.BigInteger, db.ForeignKey(User.character_id), primary_key=True)
    date = db.Column(db.Date(), primary_key=True)
    solar_system_id = db.Column(db.BigInteger, primary_key=True)
    type_id = db.Column(db.BigInteger, primary_key=True)
    quantity = db.Column(db.BigInteger)
    ore_name = db.Column(db.String(100))
    volume = db.Column(db.Float)

# -----------------------------------------------------------------------
# Flask Login requirements
# -----------------------------------------------------------------------
@login_manager.user_loader
def load_user(character_id):
    """ Required user loader for Flask-Login """
    return User.query.get(character_id)


# -----------------------------------------------------------------------
# ESIPY Init
# -----------------------------------------------------------------------
# create the app
esiapp = App.create(config.ESI_SWAGGER_JSON)

# init the security object
esisecurity = EsiSecurity(
    app=esiapp,
    redirect_uri=config.ESI_CALLBACK,
    client_id=config.ESI_CLIENT_ID,
    secret_key=config.ESI_SECRET_KEY,
)

# init the client
esiclient = EsiClient(
    security=esisecurity,
    cache=None,
    headers={'User-Agent': config.ESI_USER_AGENT}
)


# -----------------------------------------------------------------------
# Login / Logout Routes
# -----------------------------------------------------------------------
def generate_token():
    """Generates a non-guessable OAuth token"""
    chars = ('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
    rand = random.SystemRandom()
    random_string = ''.join(rand.choice(chars) for _ in range(40))
    return hmac.new(
        config.SECRET_KEY,
        random_string,
        hashlib.sha256
    ).hexdigest()


@app.route('/sso/login')
def login():
    """ this redirects the user to the EVE SSO login """
    token = generate_token()
    session['token'] = token
    return redirect(esisecurity.get_auth_uri(
        scopes=['esi-industry.read_character_mining.v1'],
        state=token,
    ))


@app.route('/sso/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.route('/sso/callback')
def callback():
    """ This is where the user comes after he logged in SSO """
    # get the code from the login process
    code = request.args.get('code')
    token = request.args.get('state')

    # compare the state with the saved token for CSRF check
    sess_token = session.pop('token', None)
    if sess_token is None or token is None or token != sess_token:
        return 'Login EVE Online SSO failed: Session Token Mismatch', 403

    # now we try to get tokens
    try:
        auth_response = esisecurity.auth(code)
    except APIException as e:
        return 'Login EVE Online SSO failed: %s' % e, 403

    # we get the character informations
    cdata = esisecurity.verify()

    # if the user is already authed, we log him out
    if current_user.is_authenticated:
        logout_user()

    # now we check in database, if the user exists
    # actually we'd have to also check with character_owner_hash, to be
    # sure the owner is still the same, but that's an example only...
    try:
        user = User.query.filter(
            User.character_id == cdata['CharacterID'],
        ).one()

    except NoResultFound:
        user = User()
        user.character_id = cdata['CharacterID']

    user.character_owner_hash = cdata['CharacterOwnerHash']
    user.character_name = cdata['CharacterName']
    user.update_token(auth_response)

    # now the user is ready, so update/create it and log the user
    try:
        db.session.merge(user)
        db.session.commit()

        login_user(user)
        session.permanent = True

    except:
        logger.exception("Cannot login the user - uid: %d" % user.character_id)
        db.session.rollback()
        logout_user()

    return redirect(url_for("index"))


# -----------------------------------------------------------------------
# Character Data Routes
# ----------------------------------------------------------------------
def _get_character_data(character):
    # For a given character, crawl all the history of the api.
    wallet = None
    data = []
    if character.is_authenticated:
        # give the token data to esisecurity, it will check alone
        # if the access token need some update
        esisecurity.update_token(character.get_sso_data())
        # Get all the pages
        try:
            page_num = 1
            while True:
                print page_num
                op = esiapp.op['get_characters_character_id_mining'](
                    character_id=character.character_id,
                    page=page_num
                )
                mining = esiclient.request(op)
                data += mining.data
                page_num += 1
                if len(mining.data) == 0:
                    break
        except Exception as e:
            print e

    print character.character_name

    for row in data:
        obj = MiningData()
        obj.character_id = character.character_id
        obj.date = datetime.strptime(str(row.get('date')), '%Y-%m-%d')
        obj.solar_system_id = row.get('solar_system_id')
        obj.type_id = row.get('type_id')
        obj.quantity = row.get('quantity')

        op = esiapp.op['get_universe_types_type_id'](type_id=row.get('type_id') )
        ore = esiclient.request(op).data
        obj.ore_name = ore.get("name")
        obj.volume = ore.get("volume")

        #op = esiapp.op['get_universe_systems_system_id'](system_id=data[0].solar_system_id )
        #obj.system_name = esiclient.request(op).data.get("name")
        db.session.add(obj)

        try:
            db.session.commit()
        except Exception as e:
            print("Duplicate entry")
            print obj
            db.session.rollback()

@app.route('/update')
def update():
    # Pull new data for character.
    character_id = request.args.get('character_id', 0, type=int)
    character = User.query.filter_by(character_id=character_id).all()[0]
    _get_character_data(character)
    return jsonify(result={})

# -----------------------------------------------------------------------
# Index Routes
# -----------------------------------------------------------------------

ORES = ['Gleaming Spodumain', 'Obsidian Ochre', 'Crystalline Crokite', 'Prismatic Gneiss', 'Prime Arkonor', 'Monoclinic Bistot',  'Vitreous Mercoxit']
COLORS = ['#b3b3b3', '#1a1a1a', '#eeee33', '#33ff33', '#ff3333', '#33ffff', '#ff9933']

COLOR_MAP = {'Gleaming Spodumain': '#b3b3b3',
             'Obsidian Ochre': '#1a1a1a',
             'Crystalline Crokite': '#eeee33',
             'Prismatic Gneiss': '#33ff33',
             'Prime Arkonor': '#ff3333',
             'Monoclinic Bistot': '#33ffff',
             'Vitreous Mercoxit': '#ff9933'
}

def _getTimeChartData():
    # Data for combined chart
    result = MiningData.query.with_entities(MiningData.date, MiningData.ore_name, func.sum(MiningData.quantity * MiningData.volume)).group_by(MiningData.date, MiningData.ore_name).order_by(MiningData.date).all()
    ore_split = {}
    for row in result:
        if ore_split.get(row[1]):
            lst = ore_split[row[1]]
            lst.append([row[0],  row[2]])
            ore_split[row[1]] = lst
        else:
            ore_split[row[1]] = [[row[0],  row[2]]]
    ret = []
    for k, v in ore_split.iteritems():
        rework = {'name': k, 'data': v, 'color': COLOR_MAP[k]}
        ret.append(rework)
    return ret

def _getCharacterChartData():
    # Really ugly way of transforming DB data to something highcharts likes.
    characters = User.query.all()
    result = MiningData.query.order_by(MiningData.date.desc())

    data = []
    charNames = []
    for character in characters:
        mined = MiningData.query.with_entities(MiningData.ore_name, func.sum(MiningData.quantity * MiningData.volume)).filter_by(character_id=character.character_id).group_by(MiningData.ore_name).all()
        charData = []
        for item in mined:
            charData.append(item)
        charNames.append(character.character_name)
        data.append(charData)

    oreData = []
    i = 0
    for ore in ORES:
        seriesData = []
        for charData in data:
            found = False
            for element in charData:
                if element[0] == ore:
                    found = True
                    break
            if found is True:
                seriesData.append(element[1])
            else:
                seriesData.append(0)
        oreSeries = {'name': ore, 'data': seriesData, 'color': COLORS[i]}
        oreData.append(oreSeries)
        i += 1
    return charNames, oreData

@app.route('/')
def index():
    # Simply display page with data.
    characters = User.query.all()
    result = MiningData.query.order_by(MiningData.date.desc())

    data = []
    for row in result:
        ret = {'date': row.date,
               'character_name':  User.query.filter_by(character_id=row.character_id).all()[0].character_name,
               'ore_name': row.ore_name,
               'quantity': row.quantity,
               'volume': row.volume}
        data.append(ret)

    char_chart_names, char_chart_data = _getCharacterChartData()
    chart_data = _getTimeChartData()

    return render_template('base.html', **{
        'characters': characters,
        'data': data,
        'chart_data': chart_data,
        'char_chart_names': char_chart_names,
        'char_chart_data': char_chart_data
    })


if __name__ == '__main__':
    app.run(port=config.PORT, host=config.HOST)
