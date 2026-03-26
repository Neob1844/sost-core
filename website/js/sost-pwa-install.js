// SOST PWA Install Helper
// Captures beforeinstallprompt and provides install function
(function() {
  var deferredPrompt = null;

  window.addEventListener('beforeinstallprompt', function(e) {
    e.preventDefault();
    deferredPrompt = e;
    // Update any app links to show "INSTALL" instead of "App"
    var links = document.querySelectorAll('a[href*="sost-app"]');
    links.forEach(function(a) {
      a.textContent = '📲 Install App';
      a.style.fontWeight = '700';
    });
  });

  window.sostInstallApp = function(e) {
    if (e) e.preventDefault();
    if (deferredPrompt) {
      deferredPrompt.prompt();
      deferredPrompt.userChoice.then(function(result) {
        if (result.outcome === 'accepted') {
          var links = document.querySelectorAll('a[href*="sost-app"]');
          links.forEach(function(a) { a.textContent = '✓ Installed'; });
        }
        deferredPrompt = null;
      });
    } else {
      // Fallback: navigate to app
      window.location.href = 'sost-app/';
    }
  };

  // Make app links trigger install instead of navigate
  document.addEventListener('click', function(e) {
    var link = e.target.closest('a[href*="sost-app"]');
    if (link && deferredPrompt) {
      e.preventDefault();
      window.sostInstallApp();
    }
  });
})();
