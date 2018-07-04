console.log('ayy');

$(function() {
    $('a.update').bind('click', function() {
        var id = this.id
        $.getJSON($SCRIPT_ROOT + '/update', {
            character_id:  id
        }, function(data) {
          $("#result").text(data.result);
        });
        return false;
    });

    var timeChart = Highcharts.chart('container', {
        title: {
            text: 'Total Mining'
        },
        xAxis: {
            title: {
                text: 'Data'
            },
            type: 'bar',
            /*
            labels: {
                formatter: function () {
                    console.log(this)
                    return Highcharts.dateFormat('%Y %b %d', this.value);
                },
            },

            dateTimeLabelFormats: {
                minute: '%H:%M',
                hour: '%H:%M',
                day: '%e. %b',
                week: '%e. %b',
                month: '%b \'%y',
                year: '%Y'
            }
            */
        },
        yAxis: {
            title: {
                text: 'Quantity mined'
            }
        },
        series: [chart_data],
    });

    /*
    $.each(chart_data, function(k, v) {
        var items = []
        $.each(v, function(k2, v2) {
            var parts = v2[0].split(' ');
            var bla = [new Date(parseInt(parts[0], 10), parseInt(parts[1], 10), parseInt(parts[2], 10)).getTime(), v2[1] ];
            items.push(bla);
        });
        console.log(items)
        timeChart.addSeries({name: k, data: v}, false);
    });

    console.log(chart_data)
    */
    // what if the actual series axises are not being set to datetime?
    timeChart.redraw();

    characterChart = Highcharts.chart('container2', {
        chart: {
            type: 'bar'
        },
        title: {
            text: 'Ore Volumes Mined By Character'
        },
        xAxis: {
            categories: char_chart_names,
            title: {
                text: null
            }
        },
        yAxis: {
            min: 0,
            title: {
                text: 'Volume (m3)',
                align: 'high'
            },
            labels: {
                overflow: 'justify'
            }
        },
        tooltip: {
            valueSuffix: ' m3'
        },
        plotOptions: {
            bar: {
                dataLabels: {
                    enabled: true
                },
                pointPadding: 0,
                groupPadding: 0,
                pointWidth: 10
            }
        },
        legend: {
            layout: 'horizontal',
            align: 'right',
            verticalAlign: 'top',
            x: -40,
            floating: false,
            borderWidth: 1,
            backgroundColor: ((Highcharts.theme && Highcharts.theme.legendBackgroundColor) || '#FFFFFF'),
            shadow: true
        },
        credits: {
            enabled: false
        },
        series: char_chart_data
    });
});
