/* globals django, google, transactionReportData */

django.jQuery(function($) {
  'use strict';

  var $module = $('#id_transaction_report'),
    $chart = $('#transaction-report-chart'),
    normalStyles = {
      lines: ['#79aec8', '#666'],
      lineWidth: 4,
      background: '#f9f9f9',
      lengendTextStyle: {
        color: '#000',
        fontSize: 13
      }
    },
    standoutStyles = {
      // colours optimised for philips tv
      lines: ['#6f6', '#F3513F'],
      lineWidth: 10,
      background: '#111',
      lengendTextStyle: {
        color: '#fff',
        fontSize: 24
      }
    },
    chartData;

  if (!$chart) {
    return;
  }

  google.charts.load('current', {packages: ['corechart']});
  google.charts.setOnLoadCallback(chartsLoaded);

  function chartsLoaded() {
    chartData = new google.visualization.DataTable();
    for (var column in transactionReportData.columns) {
      if (transactionReportData.columns.hasOwnProperty(column)) {
        column = transactionReportData.columns[column];
        chartData.addColumn(column.type, column.title);
      }
    }
    chartData.addRows(transactionReportData.rows);

    drawTransactionReports();
  }

  function drawTransactionReports() {
    var chart = new google.visualization.LineChart($chart[0]),
      styles = $module.hasClass('mtp-dashboard-module-standout') ? standoutStyles : normalStyles;

    chart.draw(chartData, {
      hAxis: {
        baselineColor: 'none',
        gridlines: {count: 0}
      },
      vAxis: {
        minValue: 0,
        baselineColor: 'none',
        gridlines: {count: 0}
      },
      chartArea: {
        top: 10,
        bottom: 10,
        left: 10
      },
      fontName: '"Roboto", "Lucida Grande", Verdana, Arial, sans-serif',
      legend: {
        alignment: 'center',
        textStyle: styles.lengendTextStyle
      },
      backgroundColor: styles.background,
      colors: styles.lines,
      lineWidth: styles.lineWidth
    });
  }

  $module.on('mtp.dashboard-standout', function() {
    $chart.empty();
    drawTransactionReports();
  })
});
