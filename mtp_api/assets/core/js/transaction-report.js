google.charts.load('current', {packages: ['corechart']});
google.charts.setOnLoadCallback(drawTransactionReports);

function drawTransactionReports() {
  'use strict';

  var chartElement = document.getElementById('transaction-report-chart');
  if (!chartElement) {
    return;
  }

  var data = new google.visualization.DataTable(),
    colours = [],
    trendlines = {};
  for (var column in transactionReportData.columns) {
    trendlines[column] = {tooltip: false};
    column = transactionReportData.columns[column]
    data.addColumn(column.type, column.title);
    if (column.colour) {
      colours.push(column.colour);
    }
  }
  data.addRows(transactionReportData.rows);

  var chart = new google.visualization.LineChart(chartElement);
  chart.draw(data, {
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
    backgroundColor: '#f9f9f9',
    colors: colours,
    trendlines: trendlines
  });
}
