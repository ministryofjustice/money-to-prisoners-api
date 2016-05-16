/* globals django */

django.jQuery(function($) {
  'use strict';

  var $pageBackground = $('html, body'),
    $dashboardWrapper = $('#mtp-dashboard'),
    cookieName = $dashboardWrapper.data('cookie-name'),
    standoutCookieName = $dashboardWrapper.data('standout-cookie-name'),
    $dashboardModules = $('.mtp-dashboard-module'),
    $moduleForms = $('.mtp-dashboard-change form'),
    $standoutModule = $('#' + Cookies.get(standoutCookieName)),
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


  // dashboard module forms

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

  $dashboardModules.on('mtp.dashboard-standout', function(e, $module) {
    if($module.hasClass('mtp-dashboard-module-standout')) {
      $dashboardModules.css('visibility', 'visible');
      $module.removeClass('mtp-dashboard-module-standout');
      $pageBackground.css('background', '#fff');
      Cookies.remove(standoutCookieName);
    } else {
      $dashboardModules.not($module).css('visibility', 'hidden');
      $module.addClass('mtp-dashboard-module-standout');
      $pageBackground.css('background', $module.css('background'));
      Cookies.set(standoutCookieName, $module.attr('id'));
    }
  });

  $('.js-mtp-dashboard-standout').click(function(e) {
    e.preventDefault();
    var $module = $(this).closest('.mtp-dashboard-module');
    $module.trigger('mtp.dashboard-standout', [$module])
  });

  if ($standoutModule.size()) {
    $standoutModule.trigger('mtp.dashboard-standout', [$standoutModule]);
  }
});
