google.charts.load('current', {'packages':['corechart']});

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

  vAxis:{
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
  chartArea: {
    left: 10,
    right: 20,
    top: 70,
    width: '50%',
    height: '70%'
  },
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
  }
};

function drawDigitalTakeUp() {
   var data = new google.visualization.DataTable();
      data.addColumn('date', 'Month');
      data.addColumn('number', 'Digital');
      data.addColumn('number', 'Post');

      data.addRows(digitalTakeupData);

    var chart = new google.visualization.LineChart(document.getElementById('digital_take_up'));
    var options = Object.assign(sharedOptions);
    options.colors =  ['#85994B', '#2B8CC4']
    options.lineWidth = 10,
    chart.draw(data, options);
}

function drawChartCredit() {
  var data = google.visualization.arrayToDataTable(creditData);

  var view = new google.visualization.DataView(data);
  view.setColumns([
    0,
    1,
    {
      sourceColumn: 1,
      role: "annotation",
    },
    2,
    {
      sourceColumn: 2,
      role: "annotation" ,
    },
    3,
    {
      sourceColumn: 3,
      role: "annotation" ,
    }
  ]);

  var chart = new google.visualization.ColumnChart(document.getElementById('credit_bar_chart'));
  var options = Object.assign(sharedOptions);
  options.colors = ['#FFBF47', '#D53880', '#6F72AF'];
  chart.draw(view, options);
}

function drawChartDisbursmentCount() {
  var data = google.visualization.arrayToDataTable(disbursementData);

  var view = new google.visualization.DataView(data);
  view.setColumns([
    0,
    1,
    {
      sourceColumn: 1,
      role: "annotation"
    },
    2,
    {
      sourceColumn: 2,
      role: "annotation"
    },
  ]);

  var chart = new google.visualization.ColumnChart(document.getElementById('disbursements_count_chart'));
  var options = Object.assign(sharedOptions);
  options.vAxis.title = 'Credits';
  options.colors = ['#2B8CC4', '#D53880'];
  chart.draw(view, options);
}

var credit_bar_chart_title;
var digital_take_up_title;
var transaction_bar_chart;
var digital_take_up;
var digital_takeup_legend;
var credits_legend;
var table_1;
var table_2;
var tableID=2;
var loadedCharts1 = false;
var loadedCharts2 = false;
var loadedCharts3 = false;

function changeTable(){
  if(tableID % 2 == 0){
    table_1.style.display = 'block';
    table_2.style.display = 'none';
    if(loadedCharts1 == false){
      drawChartCredit();
      drawDigitalTakeUp();
      loadedCharts1 = true;
      loadedCharts3 = true;
    }

    setTimeout(function() {
      digital_take_up_title.style.display = 'block';
      digital_takeup_legend.style.display = 'block';
      digital_take_up.style.display = 'block';

      credit_bar_chart_title.style.display = 'none';
      credits_legend.style.display = 'none';
      credit_bar_chart.style.display = 'none';
    }, 4000);

  } else {
    digital_take_up_title.style.display = 'none';
    credit_bar_chart_title.style.display = 'block';
    digital_take_up.style.display = 'none';
    credit_bar_chart.style.display = 'block'
    credits_legend.style.display = 'block';
    digital_takeup_legend.style.display = 'none';

    table_1.style.display = 'none';
    table_2.style.display = 'block';
    if(loadedCharts2 == false){
      drawChartDisbursmentCount();
      loadedCharts2 = true;
    }
  }
   tableID+=1;
}

function initializeCharts() {
  table_1 = document.getElementById('table_1');
  table_2 = document.getElementById('table_2');
  digital_takeup_legend = document.getElementById('digital_takeup_legend');
  credits_legend = document.getElementById('credits_legend');
  digital_take_up = document.getElementById('digital_take_up');
  credit_bar_chart = document.getElementById('credit_bar_chart');
  credit_bar_chart_title = document.getElementById('credit_bar_chart_title');
  digital_take_up_title = document.getElementById('digital_take_up_title');

  changeTable();
  setInterval(changeTable, 8000);
}

 google.charts.setOnLoadCallback(initializeCharts);
