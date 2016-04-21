/* globals django */

django.jQuery(function($) {
  'use strict';

  var $pageBackground = $('html, body'),
    $dashboardWrapper = $('#mtp-dashboard'),
    cookieName = $dashboardWrapper.data('cookie-name'),
    standoutCookieName = $dashboardWrapper.data('standout-cookie-name'),
    $moduleForms = $('.mtp-dashboard-change form'),
    autoreloadInterval;


  // dashboard auto-reload

  function startDashboardAutoreload() {
    autoreloadInterval = setInterval(function() {
      window.location.reload();
    }, parseInt($dashboardWrapper.data('reload-interval'), 10) * 1000 || 1000)
  }

  $('#mtp-dashboard-autoreload input').click(function() {
    if($(this).is(':checked')) {
      startDashboardAutoreload();
    } else {
      clearInterval(autoreloadInterval);
    }
  });

  startDashboardAutoreload();


  // dashboard module fomrs

  $('.js-mtp-dashboard-change').each(function() {
    var $changeLink = $(this),
      $changeWrapper = $changeLink.closest('.mtp-dashboard-module').find('.mtp-dashboard-change');

    $changeLink.click(function(e) {
      e.preventDefault();
      $changeWrapper.toggle();
    });
  });

  $moduleForms.change(function() {
    // save forms as cookie
    var moduleFormCookie = {};
    $moduleForms.each(function() {
      var $form = $(this),
        cookieKey = $form.data('cookie-key');
      if(cookieKey) {
        moduleFormCookie[cookieKey] = $form.serialize();
      }
    });
    Cookies.set(cookieName, moduleFormCookie, {expires: 2});

    // reload page
    window.location.reload();
  });


  // dashboard module stand-out

  $('.mtp-dashboard-module').on('mtp.dashboard-standout', function(e, $module, $standoutLink) {
    if($module.hasClass('mtp-dashboard-module-standout')) {
      $module.removeClass('mtp-dashboard-module-standout');
      $standoutLink.text($standoutLink.data('title-standout'));
      $pageBackground.css('background', '#fff');
      Cookies.remove(standoutCookieName);
    } else {
      $module.addClass('mtp-dashboard-module-standout');
      $standoutLink.text($standoutLink.data('title-no-standout'));
      $pageBackground.css('background', $module.css('background'));
      Cookies.set(standoutCookieName, $module.attr('id'));
    }
  });

  $('.js-mtp-dashboard-standout').click(function(e) {
    var $standoutLink = $(this),
      $module = $standoutLink.closest('.mtp-dashboard-module');

    e.preventDefault();
    $module.trigger('mtp.dashboard-standout', [$module, $standoutLink])
  });

  $('#' + Cookies.get(standoutCookieName) + ' .js-mtp-dashboard-standout').click();
});
