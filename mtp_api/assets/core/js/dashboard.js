django.jQuery(function($) {
  var dashboardWrapper = $('#mtp-dashboard'),
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
});
