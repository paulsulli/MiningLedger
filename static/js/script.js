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

    var myChart = Highcharts.chart('container', {
        title: {
            text: 'Total Mining'
        },
        xAxis: {
            title: {
                text: 'Data'
            },
            type: 'datetime',
            labels: {
                formatter: function () {
                    return Highcharts.dateFormat('%Y %b %d', this.value);
                },
                dateTimeLabelFormats: {
                    minute: '%H:%M',
                    hour: '%H:%M',
                    day: '%e. %b',
                    week: '%e. %b',
                    month: '%b \'%y',
                    year: '%Y'
                }
            }
        },
        yAxis: {
            title: {
                text: 'Quantity mined'
            }
        },
        series: [],
    });

    var series = [];
    $.each(chart_data, function(k, v) {
        items = []
        $.each(v, function(k2, v2) {
            var parts = v2[0].split(' ');
            var bla = [ Date.UTC(parseInt(parts[0], 10), parseInt(parts[1], 10), parseInt(parts[2], 10)), v2[1] ];
            items.push(bla);
        });
        console.log(items)
        myChart.addSeries({name: k, data: v}, false);
    });

    myChart.redraw();
});

