/* globals django, google, satisfactionResultsData */

django.jQuery(function($) {
  'use strict';

  var colourScale = ['#ff800e', '#ffbc79', '#cfcfcf', '#a2c8ec', '#5f9ed1', '#dcdcdc'];
  var colours = ['#666', '#79aec8'];
  var font = 'Roboto, "Lucida Grande", Verdana, Arial, sans-serif';

  google.charts.setOnLoadCallback(function() {
    $.each(satisfactionResultsData.questions, function(index, question) {
        var $chart = $('#satisfaction-results-chart-' + index),
          chartData = new google.visualization.DataTable();

        for (var column in satisfactionResultsData.columns) {
          if (satisfactionResultsData.columns.hasOwnProperty(column)) {
            chartData.addColumn(satisfactionResultsData.columns[column]);
          }
        }
        chartData.addRows(question.rows);

        drawTransactionReports($chart, chartData, question.means);
    });
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
      var $svg = $chart.find('svg');
      var svgNamespace = $svg[0].namespaceURI;
      var cli = chart.getChartLayoutInterface();
      var legendBounds = cli.getBoundingBox('legend');
      var chartBounds = cli.getChartAreaBoundingBox();
      var significantWidth = chartBounds.width * 5 / 6;  // last option is disregarded
      var meanMarkerWidth = 12;
      var $hideOnMouseover = [];
      var $chartDetails, $title, i;

      $chartDetails = $($svg.children('g')[1]).children('g');
      $chartDetails = $($chartDetails[0]).add($chartDetails[$chartDetails.length - 1]).attr({
        visibility: 'hidden'
      });

      // draw coloured tabs
      for (i in colourScale) {
        if (colourScale.hasOwnProperty(i)) {
          var colour = colourScale[i];
          var barBounds = cli.getBoundingBox('bar#0#' + i);
          var $rect = $(document.createElementNS(svgNamespace, 'rect'));
          $rect.attr({
            x: barBounds.left,
            y: barBounds.top + barBounds.height + 2,
            width: barBounds.width * means.length,
            height: 3,
            fill: colour
          });
          $svg.append($rect);
          $hideOnMouseover.push($rect);
        }
      }

      // draw mean bars
      for (i in means) {
        if (means.hasOwnProperty(i)) {
          var mean = means[i];
          var $meanMarker = $(document.createElementNS(svgNamespace, 'rect'));
          var $meanTextMarker = $(document.createElementNS(svgNamespace, 'text'));
          var x, y;
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

      // add title to legend
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
