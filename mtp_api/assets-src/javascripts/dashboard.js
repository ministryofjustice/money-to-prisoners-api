/* globals Cookies */

django.jQuery(function ($) {
  'use strict';

  var $dashboardWrapper = $('#mtp-dashboard');
  var cookieName = $dashboardWrapper.data('cookie-name');
  var $moduleForms = $('.mtp-dashboard-change form');
  var autoreloadInterval = null;

  // dashboard auto-reload

  function startDashboardAutoreload () {
    autoreloadInterval = setInterval(function () {
      window.location.reload();
    }, (parseInt($dashboardWrapper.data('reload-interval'), 10) || 600) * 1000);
  }

  $('#mtp-dashboard-autoreload input').click(function () {
    if ($(this).is(':checked')) {
      startDashboardAutoreload();
    } else {
      clearInterval(autoreloadInterval);
    }
  });

  startDashboardAutoreload();


  // dashboard module forms

  $('.js-mtp-dashboard-change').each(function () {
    var $changeLink = $(this);
    var $changeWrapper = $changeLink.closest('.mtp-dashboard-module').find('.mtp-dashboard-change');

    $changeLink.click(function (e) {
      e.preventDefault();
      $changeWrapper.toggle();
    });
    if ($changeWrapper.find('form').is('.invalid')) {
      $changeWrapper.show();
    }
  });

  function saveDashboardFormsAndReload (e) {
    // save forms as cookie
    if (e && e.preventDefault) {
      e.preventDefault();
    }
    var moduleFormCookie = {};
    $moduleForms.each(function () {
      var $form = $(this);
      var cookieKey = $form.data('cookie-key');

      if (cookieKey) {
        moduleFormCookie[cookieKey] = $form.serialize();
      }
    });
    Cookies.set(cookieName, JSON.stringify(moduleFormCookie), {expires: 2});

    // reload page
    window.location.reload();
  }

  $moduleForms.filter('.mtp-auto-reload').change(saveDashboardFormsAndReload);
  $moduleForms.filter(':not(.mtp-auto-reload)').on('click', ':submit', saveDashboardFormsAndReload);


  // dashboard full-screen

  $('.mtp-dashboard-toggle-full-screen').click(function (e) {
    var $button = $(this);
    var dashboardWrapper = $dashboardWrapper[0];
    var prefixes = ['', 'webkit', 'moz', 'ms'];
    e.preventDefault();
    $button.text($button.data('close-label'));
    $button.off('click');
    for (var prefix in prefixes) {
      if (Object.prototype.hasOwnProperty.call(prefixes, prefix)) {
        var method = prefixes[prefix] ? prefixes[prefix] + 'RequestFullscreen' : 'requestFullscreen';
        if (dashboardWrapper[method]) {
          dashboardWrapper[method]();
          return;
        }
      }
    }
  });
});
