/* globals django, google, satisfactionResultsData */

django.jQuery(function($) {
  'use strict';

  var colourScale = ['#ff800e', '#ffbc79', '#cfcfcf', '#a2c8ec', '#5f9ed1', '#dcdcdc'],
    colours = ['#666', '#79aec8'],
    font = 'Roboto, "Lucida Grande", Verdana, Arial, sans-serif';

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

        drawTransactionReports($chart, chartData, [question.mean, null]);
      }
    }
  });

  function drawTransactionReports($chart, chartData, means) {
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
      fontName: font,
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
        $hideOnMouseover = [],
        $chartDetails, $title,
        i;

      $chartDetails = $($svg.children('g')[1]).children('g');
      $chartDetails = $($chartDetails[0]).add($chartDetails[$chartDetails.length - 1]).attr({
        visibility: 'hidden'
      });

      for (i in colourScale) {
        if (colourScale.hasOwnProperty(i)) {
          var colour = colourScale[i],
            barBounds = cli.getBoundingBox('bar#0#' + i),
            $rect = $(document.createElementNS(svgNamespace, 'rect'));
          $rect.attr({
            x: barBounds.left,
            y: barBounds.top + barBounds.height + 2,
            width: barBounds.width * 2,
            height: 3,
            fill: colour
          });
          $svg.append($rect);
          $hideOnMouseover.push($rect);
        }
      }

      for (i in means) {
        if (means.hasOwnProperty(i)) {
          var mean = means[i],
            $meanMarker = $(document.createElementNS(svgNamespace, 'rect')),
            $meanTextMarker = $(document.createElementNS(svgNamespace, 'text')),
            x, y;
          if (mean === null) {
            x = chartBounds.width * (1 - (1 / 6) + (1 / 12));
          } else {
            x = significantWidth * (2 + mean) / 4
          }
          x = chartBounds.left + x - meanMarkerWidth / 2;
          y = chartBounds.top;
          $meanMarker.attr({
            x: x,
            y: y,
            width: meanMarkerWidth,
            height: chartBounds.height,
            fill: colours[i]
          });
          x += 1;
          y = chartBounds.top + chartBounds.height / 2;
          $meanTextMarker.attr({
            x: x,
            y: y - 2,
            transform: 'rotate(90,' + x + ',' + y + ')',
            fill: '#fff',
            'text-anchor': 'middle',
            'text-align': 'center',
            'font-family': font,
            'font-size': 10
          }).text('Average response');
          $hideOnMouseover.push($meanMarker);
          $hideOnMouseover.push($meanTextMarker);
        }
      }
      $svg.append($hideOnMouseover);

      $title = $(document.createElementNS(svgNamespace, 'text'));
      $title.text($chart.data('title'));
      $title.attr({
        x: legendBounds.left,
        y: legendBounds.top - 6,
        fill: '#000',
        'font-family': font,
        'font-weight': 'bold',
        'font-size': 13
      });
      $svg.append($title);

      $svg.on('mouseover', function() {
        $chartDetails.attr({
          visibility: 'visible'
        });
        $.each($hideOnMouseover, function() {
          $(this).attr({
            visibility: 'hidden'
          });
        });
      }).on('mouseout', function() {
        $chartDetails.attr({
          visibility: 'hidden'
        });
        $.each($hideOnMouseover, function() {
          $(this).attr({
            visibility: 'visible'
          });
        });
      });
    });
  }
});
