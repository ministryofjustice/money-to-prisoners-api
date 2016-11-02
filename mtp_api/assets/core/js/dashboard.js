/* globals django */

django.jQuery(function($) {
  'use strict';

  var $pageBackground = $('html, body');
  var $dashboardWrapper = $('#mtp-dashboard');
  var cookieName = $dashboardWrapper.data('cookie-name');
  var standoutCookieName = $dashboardWrapper.data('standout-cookie-name');
  var $dashboardModules = $('.mtp-dashboard-module');
  var $moduleForms = $('.mtp-dashboard-change form');
  var $standoutModule = $('#' + Cookies.get(standoutCookieName));
  var autoreloadInterval;


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

  function saveDashboardFormsAndReload(e) {
    // save forms as cookie
    if(e && e.preventDefault) {
      e.preventDefault();
    }
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
  }

  $moduleForms.filter('.mtp-auto-reload').change(saveDashboardFormsAndReload);
  $moduleForms.filter(':not(.mtp-auto-reload)').on('click', ':submit', saveDashboardFormsAndReload);


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
