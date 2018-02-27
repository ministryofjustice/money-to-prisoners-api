/* globals django, google, performanceData */
'use strict';

function performanceChart ($, data, $chart) {
  var options = {
    // colours and sizes optimised for full-screen on philips tv
    fontName: 'Roboto, "Lucida Grande", Verdana, Arial, sans-serif',
    colors: ['#66f', '#6f6', '#ff6'],
    backgroundColor: '#000',
    hAxis: {
      format: 'd MMM',
      slantedText: true,
      baselineColor: '#ccc',
      textStyle: {color: '#ccc'},
      gridlines: {
        count: data.weekCount,
        color: '#000'
      }
    },
    vAxis: {
      minValue: 0,
      maxValue: data.maxValue,
      format: 'short',
      baselineColor: '#ccc',
      textStyle: {color: '#ccc'},
      textPosition: 'in',
      gridlines: {
        count: 5,
        color: '#333'
      }
    },
    chartArea: {
      top: 30,
      right: 0,
      bottom: 50,
      left: 0
    },
    isStacked: false,
    bar: {
      groupWidth: '61.8%'
    },
    annotations: {
      textStyle: {
        fontSize: 36,
        fontWeight: 'bold'
      }
    },
    legend: {
      position: 'top',
      alignment: 'end',
      maxLines: 1,
      textStyle: {
        color: '#ccc',
        fontSize: 26
      }
    }
  };
  var chartData = new google.visualization.DataTable(data.chart);
  var chart = new google.visualization.ColumnChart($chart[0]);

  chart.draw(chartData, options);

  google.visualization.events.addListener(chart, 'ready', function () {
    var $svg = $chart.find('svg');
    var svgNamespace = $svg[0].namespaceURI;
    var cli = chart.getChartLayoutInterface();
    var legendBounds = cli.getBoundingBox('legend');
    var $title = $(document.createElementNS(svgNamespace, 'text'));
    $title.text(data.title);
    $title.attr({
      'x': 0,
      'y': legendBounds.top + options.legend.textStyle.fontSize,
      'fill': options.legend.textStyle.color,
      'text-anchor': 'start',
      'font-family': options.fontName,
      'font-size': options.legend.textStyle.fontSize
    });
    $svg.append($title);
  });
}

django.jQuery(function ($) {
  var $container = $('#id_performance_overview');
  if ($container.length !== 1) {
    return;
  }

  var $chart = $('#performance-overview-chart');
  if (performanceData && $chart.length === 1) {
    google.charts.setOnLoadCallback(function () {
      performanceChart($, performanceData, $chart);
    });
  }

  var container = $container[0];
  var $titles = $('.performance-overview-title div', container);
  var $pages = $('dl', container);
  var $animatedElements = $('.transition-show', container);
  var pageIndex = 0;

  function render () {
    $titles.hide();
    $($titles.get(pageIndex)).show();
    $pages.hide();
    $($pages.get(pageIndex)).show();
    $animatedElements.addClass('transition-showing');
    $animatedElements.filter(':visible').each(function (i) {
      var $animatedElement = $(this);
      setTimeout(function () {
        $animatedElement.removeClass('transition-showing');
      }, i * 250);
    });
    pageIndex = (pageIndex + 1) % $pages.length;
  }

  render();
  setInterval(render, 10000);
});
