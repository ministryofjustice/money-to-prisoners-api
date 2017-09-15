/* globals django, google, creditReportData */

django.jQuery(function ($) {
  'use strict';

  // change form

  var $customDateRows = $('.row_start_date, .row_end_date');
  $('#id_date_range').change(function () {
    if ($(this).val() === 'custom') {
      $customDateRows.show();
    } else {
      $customDateRows.hide();
    }
  }).change();

  // chart

  var $module = $('#id_credit_report');
  var $chart = $('#credit-chart');
  var normalStyles = {
    font: 'Roboto, "Lucida Grande", Verdana, Arial, sans-serif',
    lines: ['#79aec8', '#666'],
    lineWidth: 4,
    background: '#f9f9f9',
    weekendBackground: '#ebebeb',
    bar: {
      groupWidth: '70%'
    },
    annotationTextStyle: {},
    lengendTextStyle: {
      color: '#000',
      fontSize: 13
    }
  };
  var standoutStyles = {
    // colours and sizes optimised for philips tv
    font: 'Roboto, "Lucida Grande", Verdana, Arial, sans-serif',
    lines: ['#6f6', '#F3513F'],
    lineWidth: 10,
    background: '#111',
    weekendBackground: '#2b2b2b',
    bar: {
      groupWidth: '95%'
    },
    annotationTextStyle: {
      fontSize: 36,
      fontWeight: 'bold'
    },
    lengendTextStyle: {
      color: '#fff',
      fontSize: 26
    }
  };
  var chartData = null;

  if (!$chart.length || !(creditReportData.rows || []).length) {
    return;
  }

  function drawCreditReports () {
    var chart = new google.visualization.ColumnChart($chart[0]);
    var styles = $module.hasClass('mtp-dashboard-module-standout') ? standoutStyles : normalStyles;

    chart.draw(chartData, {
      hAxis: {
        baselineColor: 'none',
        gridlines: {count: 0}
      },
      vAxis: {
        minValue: 0,
        maxValue: creditReportData.max,
        baselineColor: 'none',
        gridlines: {count: 0}
      },
      chartArea: {
        top: 10,
        bottom: 10,
        left: 10
      },
      fontName: styles.font,
      annotations: {
        textStyle: styles.annotationTextStyle
      },
      legend: {
        alignment: 'center',
        textStyle: styles.lengendTextStyle
      },
      bar: styles.bar,
      isStacked: true,
      backgroundColor: styles.background,
      colors: styles.lines
    });

    google.visualization.events.addListener(chart, 'ready', function () {
      var $svg = $chart.find('svg');
      var svgNamespace = $svg[0].namespaceURI;
      var cli = chart.getChartLayoutInterface();
      var bounds = cli.getChartAreaBoundingBox();
      var dayWidth = bounds.width / creditReportData.rows.length;
      var dayHeight = bounds.height;
      var dayTop = bounds.top;
      var dayLeft = 0;
      var $chartRect = null;
      var legendBounds = cli.getBoundingBox('legend');
      var $title = $(document.createElementNS(svgNamespace, 'text'));

      $title.text(creditReportData.title);
      $title.attr({
        'text-anchor': 'start',
        x: legendBounds.left,
        y: legendBounds.top - Math.floor(styles.lengendTextStyle.fontSize / 2),
        fill: styles.lengendTextStyle.color,
        'font-family': styles.font,
        'font-weight': 'bold',
        'font-size': styles.lengendTextStyle.fontSize
      });
      $svg.append($title);

      $chart.find('rect').each(function () {
        if (this.x.baseVal.value === bounds.left &&
          this.y.baseVal.value === bounds.top &&
          this.width.baseVal.value === bounds.width &&
          this.height.baseVal.value === bounds.height) {
          $chartRect = $(this);
        }
      });

      if ($chartRect.size()) {
        for (var weekend in creditReportData.weekends) {
          if (!creditReportData.weekends.hasOwnProperty(weekend)) {
            continue;
          }
          weekend = creditReportData.weekends[weekend];
          dayLeft = cli.getXLocation(weekend) - dayWidth / 2;
          var $rect = $(document.createElementNS(svgNamespace, 'rect'));
          $rect.attr({
            x: dayLeft,
            y: dayTop,
            height: dayHeight,
            width: dayWidth,
            stroke: 'none',
            'stroke-width': 0,
            fill: styles.weekendBackground
          });
          $chartRect.after($rect);
        }
      }

    });
  }

  $module.on('mtp.dashboard-standout', function () {
    $chart.empty();
    drawCreditReports();
  });

  google.charts.setOnLoadCallback(function () {
    chartData = new google.visualization.DataTable();
    for (var column in creditReportData.columns) {
      if (creditReportData.columns.hasOwnProperty(column)) {
        chartData.addColumn(creditReportData.columns[column]);
      }
    }
    chartData.addRows(creditReportData.rows);

    drawCreditReports();
  });
});
