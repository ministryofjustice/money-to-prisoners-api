/* globals django, google, satisfactionResultsData */

django.jQuery(function($) {
  'use strict';

  var colourScale = ['#ff800e', '#ffbc79', '#cfcfcf', '#a2c8ec', '#5f9ed1', '#dcdcdc'],
    colourByPost = '#666',
    colourByMTP = '#79aec8';

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
        chartData.addRows($.map(question.rows, function(item, index) {
          item[2] = 'color: ' + colourScale[index];
          item[5] = 'color: ' + colourScale[index];
          return [item];  // because jQuery flattens returned arrays
        }));

        drawTransactionReports($chart, chartData, [colourByPost, colourByMTP], [question.mean, null]);
      }
    }
  });

  function drawTransactionReports($chart, chartData, colours, means) {
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
      colors: colours
    });

    google.visualization.events.addListener(chart, 'ready', function() {
      var $svg = $chart.find('svg'),
        svgNamespace = $svg[0].namespaceURI,
        cli = chart.getChartLayoutInterface(),
        legendBounds = cli.getBoundingBox('legend'),
        chartBounds = cli.getChartAreaBoundingBox(),
        significantWidth = chartBounds.width * 5 / 6, // last option is disregarded
        meanMarkerWidth = 12,
        $chartDetails, $meanMarkers, $title;

      $chartDetails = $($svg.children('g')[1]).children('g');
      $chartDetails = $($chartDetails[0]).add($chartDetails[$chartDetails.length - 1]).attr({
        visibility: 'hidden'
      });

      $meanMarkers = [];
      for (var i in means) {
        if (means.hasOwnProperty(i)) {
          var mean = means[i],
            $meanMarker = $(document.createElementNS(svgNamespace, 'rect')),
            x = chartBounds.left + significantWidth * (2 + mean) / 4;
          if (mean === null) {
            x = chartBounds.left + chartBounds.width * (1 - (1 / 6) + (1 / 12));
          }
          $meanMarker.attr({
            x: x - meanMarkerWidth / 2,
            y: chartBounds.top,
            height: chartBounds.height,
            width: meanMarkerWidth,
            fill: colours[i]
          });
          $meanMarkers.push($meanMarker);
        }
      }
      $svg.append($meanMarkers);

      $title = $(document.createElementNS(svgNamespace, 'text'));
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

      $svg.on('mouseover', function() {
        $chartDetails.attr({
          visibility: 'visible'
        });
        $.each($meanMarkers, function() {
          $(this).attr({
            visibility: 'hidden'
          });
        });
      }).on('mouseout', function() {
        $chartDetails.attr({
          visibility: 'hidden'
        });
        $.each($meanMarkers, function() {
          $(this).attr({
            visibility: 'visible'
          });
        });
      });
    });
  }
});
