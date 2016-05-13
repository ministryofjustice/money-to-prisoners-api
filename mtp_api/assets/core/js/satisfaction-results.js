/* globals django, google, satisfactionResultsData */

django.jQuery(function($) {
  'use strict';

  google.charts.setOnLoadCallback(function() {
    for(var question in satisfactionResultsData.questions) {
      if (satisfactionResultsData.questions.hasOwnProperty(question)) {
        question = satisfactionResultsData.questions[question];

        var $chart = $('#satisfaction-results-chart-' + question.id),
          chartData = new google.visualization.DataTable();

        for (var column in satisfactionResultsData.columns) {
          if (satisfactionResultsData.columns.hasOwnProperty(column)) {
            chartData.addColumn(satisfactionResultsData.columns[column]);
          }
        }
        chartData.addRows(question.rows);

        drawTransactionReports($chart, chartData, question.title);
      }
    }
  });

  function drawTransactionReports($chart, chartData) {
    var chart = new google.visualization.ColumnChart($chart[0]);
    chart.draw(chartData, {
      hAxis: {
        baselineColor: 'none'
      },
      vAxis: {
        minValue: 0,
        maxValue: satisfactionResultsData.max,
        baselineColor: 'none',
        gridlines: {count: 0}
      },
      chartArea: {
        top: 10,
        left: 10
      },
      fontName: 'Roboto, "Lucida Grande", Verdana, Arial, sans-serif',
      legend: {
        alignment: 'center',
        textStyle: {
          color: '#000',
          fontSize: 13
        }
      },
      backgroundColor: '#f9f9f9',
      colors: ['#79aec8']
    });

    google.visualization.events.addListener(chart, 'ready', function() {
      var $svg = $chart.find('svg'),
        cli = chart.getChartLayoutInterface(),
        legendBounds = cli.getBoundingBox('legend'),
        $title;

      $title = $(document.createElementNS($svg[0].namespaceURI, 'text'));
      $title.text($chart.data('title'));
      $title.attr({
        'text-anchor': 'start',
        x: legendBounds.left,
        y: legendBounds.top - 6,
        fill: '#000',
        'font-family': 'Roboto, "Lucida Grande", Verdana, Arial, sans-serif',
        'font-weight': 'bold',
        'font-size': 13
      });
      $svg.append($title);
    });
  }
});
