/* globals django, google, satisfactionResultsData */

django.jQuery(function($) {
  'use strict';

  google.charts.setOnLoadCallback(function() {
    var $chart = $('#satisfaction-results-chart'),
      chartData = [];

    chartData.push(satisfactionResultsData.columns);
    for (var row in satisfactionResultsData.rows) {
      if (satisfactionResultsData.rows.hasOwnProperty(row)) {
        chartData.push(satisfactionResultsData.rows[row]);
      }
    }
    chartData = google.visualization.arrayToDataTable(chartData);

    drawTransactionReports($chart, chartData);
  });

  function drawTransactionReports($chart, chartData) {
    var chart = new google.visualization.BarChart($chart[0]);

    chart.draw(chartData, {
      title: $chart.data('title'),
      hAxis: {
        baselineColor: 'none',
        viewWindowMode:'explicit',
            viewWindow: {
              max: satisfactionResultsData.max,
              min: 0
            }
      },
      vAxis: {
        baselineColor: 'none'
      },
      isStacked: true,
      chartArea: {
        top: 40,
        right: 10,
        bottom: 20,
        left: 100
      },
      fontName: 'Roboto, "Lucida Grande", Verdana, Arial, sans-serif',
      legend: {
        position: 'none'
      },
      backgroundColor: '#f9f9f9',
      colors: ['#ECC678', '#EED7B3', '#eee', '#9AAFC2', '#7593AA', '#f9f9f9']
    });
  }
});
