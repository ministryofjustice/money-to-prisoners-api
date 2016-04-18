django.jQuery(function($) {
  'use strict';

  var dashboardWrapper = $('#mtp-dashboard'),
    moduleForms = $('.mtp-dashboard-change form'),
    autoreloadInterval;

  function startDashboardAutoreload() {
    autoreloadInterval = setInterval(function() {
      window.location.reload();
    }, parseInt(dashboardWrapper.data('reload-interval'), 10) * 1000 || 1000)
  }

  $('#mtp-dashboard-autoreload input').click(function() {
    if($(this).is(':checked')) {
      startDashboardAutoreload();
    } else {
      clearInterval(autoreloadInterval);
    }
  });

  startDashboardAutoreload();

  $('.js-mtp-dashboard-change').each(function() {
    var changeLink = $(this),
      changeWrapper = changeLink.closest('.mtp-dashboard-module').find('.mtp-dashboard-change');

    changeLink.click(function(e) {
      e.preventDefault();
      changeWrapper.toggle();
    });
  });

  moduleForms.change(function() {
    // save forms as cookie
    var moduleFormCookie = {},
      cookieName = dashboardWrapper.data('cookie-name');
    moduleForms.each(function() {
      var form = $(this),
        cookieKey = form.data('cookie-key');
      if(cookieKey) {
        moduleFormCookie[cookieKey] = form.serialize();
      }
    });
    if(cookieName) {
      Cookies.set(cookieName, moduleFormCookie, {expires: 2});
    }

    // reload page
    window.location.reload();
  });
});
