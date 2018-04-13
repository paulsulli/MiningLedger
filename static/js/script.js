console.log('ayy');

$(function() {
    $('a.update').bind('click', function() {
        var id = this.id
        $.getJSON($SCRIPT_ROOT + '/update', {
            character_id:  id
        }, function(data) {
          $("#result").text(data.result);
          console.log(data.result);
        });
        return false;
    });
});