/* globals django, google, creditData, digitalTakeupData, disbursementData */

var $ = django.jQuery;
google.charts.load('current', { 'packages': ['corechart']});

var sharedOptions = {
  fontSize: 25,
  color: 'white',

  titleTextStyle: {
    fontSize: 40,
    color: 'white'
  },

  hAxis: {
    titleTextStyle: {
      fontSize: 30,
      bold: true,
      color: 'white'
    },
    textStyle: {
      fontSize: 20,
      color: 'white'
    }
  },

  vAxis: {
    titleTextStyle: {
      fontSize: 30,
      color: 'white'
    },
    textStyle: {
      fontSize: 20,
      color: 'white'
    },
    gridlines: {
      count: 4
    },
    textPosition: 'in'
  },

  backgroundColor: '#27332F',
  width: 1100,
  height: 750,

  legend: {
    position: 'none'
  },

  bar: {
    groupWidth: '90%',
    fontSize: 10,
    color: 'white'
  },

  textStyle: {
    fontSize: 10,
    color: 'white'
  },

  chartArea: {
    left: 10,
    right: 20,
    top: 70,
    height: '70%',
    width: '100%',
    backgroundColor: {
      stroke: 'white',
      strokeWidth: 1
    },
  },
};


function drawDigitalTakeUp () {
  var data = new google.visualization.DataTable();
  data.addColumn('date', 'Month');
  data.addColumn('number', 'Digital');
  data.addColumn('number', 'Post');
  data.addRows(digitalTakeupData);

  var chart = new google.visualization.LineChart(document.getElementById('digital_take_up_chart'));
  var options = Object.assign(sharedOptions);
  options.colors = ['#85994B', '#2B8CC4'];
  options.lineWidth = 10;
  chart.draw(data, options);
}

function drawChartCredit () {
  var data = google.visualization.arrayToDataTable(creditData);
  var view = new google.visualization.DataView(data);
  view.setColumns([
    0,
    1,
    {
      sourceColumn: 1,
      role: 'annotation',
    },
    2,
    {
      sourceColumn: 2,
      role: 'annotation',
    },
    3,
    {
      sourceColumn: 3,
      role: 'annotation',
    }
  ]);

  var chart = new google.visualization.ColumnChart(document.getElementById('credit_bar_chart'));
  var options = Object.assign(sharedOptions);
  options.colors = ['#FFBF47', '#D53880', '#6F72AF'];
  chart.draw(view, options);
}

function drawChartDisbursmentCount () {
  var data = google.visualization.arrayToDataTable(disbursementData);
  var view = new google.visualization.DataView(data);
  view.setColumns([
    0,
    1,
    {
      sourceColumn: 1,
      role: 'annotation',
    },
    2,
    {
      sourceColumn: 2,
      role: 'annotation',
    },
  ]);

  var chart = new google.visualization.ColumnChart(document.getElementById('disbursements_count_chart'));
  var options = Object.assign(sharedOptions);
  options.vAxis.title = 'Credits';
  options.colors = ['#2B8CC4', '#D53880'];
  chart.draw(view, options);
}

var creditsPage;
var disbursementsPage;
var digitalTakeUpChartTitle;
var digitalTakeupChartLegend;
var digitalTakeUpChart;
var creditsChartTitle;
var creditsChartLegend;
var creditsChart;
var frame = 1;
var loadFrame1 = false;
var loadFrame2 = false;
var loadFrame3 = false;
var timer;
var timeOnPage = 4000;


function disbursmentsPage () {
  creditsPage.style.display = 'none';
  disbursementsPage.style.display = 'block';
  if (loadFrame1 === false) {
    drawChartDisbursmentCount();
    loadFrame1 = true;
  }
}

function creditsPageTakeUpChart () {
  creditsPage.style.display = 'block';
  disbursementsPage.style.display = 'none';

  digitalTakeUpChartTitle.style.display = 'block';
  digitalTakeupChartLegend.style.display = 'block';
  digitalTakeUpChart.style.display = 'block';

  creditsChartTitle.style.display = 'none';
  creditsChartLegend.style.display = 'none';
  creditsChart.style.display = 'none';

  if (loadFrame2 === false) {
    drawDigitalTakeUp();
    loadFrame2 = true;
  }
}

function creditsPageMonthlyChart () {
  creditsPage.style.display = 'block';
  disbursementsPage.style.display = 'none';

  digitalTakeUpChartTitle.style.display = 'none';
  digitalTakeupChartLegend.style.display = 'none';
  digitalTakeUpChart.style.display = 'none';

  creditsChartTitle.style.display = 'block';
  creditsChartLegend.style.display = 'block';
  creditsChart.style.display = 'block';

  if (loadFrame3 === false) {
    drawChartCredit();
    loadFrame3 = true;
  }
}

function changeTable () {
  if (frame === 1) {
    disbursmentsPage();
  } else if (frame === 2) {
    creditsPageTakeUpChart();
  } else {
    creditsPageMonthlyChart();
    frame = 0;
  }

  frame += 1;
}

function initializeCharts () {
  creditsPage = document.getElementById('credits_page');
  disbursementsPage = document.getElementById('disbursements_page');
  digitalTakeUpChartTitle = document.getElementById('digital_take_up_title');
  digitalTakeupChartLegend = document.getElementById('digital_takeup_legend');
  digitalTakeUpChart = document.getElementById('digital_take_up_chart');
  creditsChartTitle = document.getElementById('credit_bar_chart_title');
  creditsChartLegend = document.getElementById('credits_legend');
  creditsChart = document.getElementById('credit_bar_chart');

  changeTable();

  timer = setInterval(changeTable, timeOnPage);

  $('#play_control').click(function (e) {
    e.preventDefault();
    if (timer) {
      clearInterval(timer);
      timer = null;
      $('#play_control').text('Start');
    } else {
      timer = setInterval(changeTable, timeOnPage);
      $('#play_control').text('Pause');
    }
  });
}

google.charts.setOnLoadCallback(initializeCharts);
