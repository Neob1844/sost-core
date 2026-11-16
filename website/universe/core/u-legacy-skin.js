/* SOST Universe — document skin (DIRECTIVA 4D §5-E).
 * Applied to document pages that keep their address at the site root. The page keeps ALL its content, scripts and links. This adds the
 * shared SOST header (eye + wordmark, the same menu, Ctrl/Cmd+K palette) and the footer directory, and hides the page's own top menu.
 * The links of that old menu are NOT lost: they are listed at the end of the page under "Previous menu of this page". The header
 * emblem animation loads after the page load (u-nav.js?v=rs20261112g). Section highlighted: window.SOSTU_SECTION = 'technology' | 'blockchain' | 'mining' | 'ecosystem'.
 * Include (root pages): <link rel="stylesheet" href="universe/core/u-legacy-skin.css"> in <head>, and before </body>:
 *   <script>window.SOSTU_NAV_FROM_ROOT=true;window.SOSTU_SECTION='technology'</script><script src="universe/core/u-nav.js?v=rs20261112g"></script><script src="universe/core/u-legacy-skin.js?v=rs20261112g"></script>
 */
(function (root) {
  'use strict';
  var U = root.SOSTU = root.SOSTU || {}, d = document;
  function bail() { d.documentElement.classList.remove('u-skin-pre'); }   // header not available: show the page's own menu again
  if (!U.nav) return bail();
  var old = null, navs = d.querySelectorAll('body > nav:not(.u-nav), body > header nav:not(.u-nav)'); if (navs.length) old = navs[0];
  var nav = d.createElement('nav'); nav.className = 'u-nav'; nav.id = 'uNav'; nav.setAttribute('aria-label', 'Primary');
  d.body.insertBefore(nav, d.body.firstChild);
  try { U.nav.render(nav, root.SOSTU_SECTION || 'technology'); } catch (e) { nav.remove(); return bail(); }
  d.documentElement.classList.add('u-skin');
  if (old) {
    var seen = {}, items = [];
    old.querySelectorAll('a[href]').forEach(function (a) { var h = a.getAttribute('href'), t = (a.textContent || '').replace(/\s+/g, ' ').trim(); if (!t || seen[h + t]) return; seen[h + t] = 1;
      // 14-Nov-2026: one Explorer (sost-explorer.html); links keep their own label
      items.push([h, t]); });
    old.classList.add('u-legacy-nav'); old.setAttribute('aria-hidden', 'true');
    var det = d.createElement('details'); det.className = 'u-legacy-links';
    det.innerHTML = '<summary>Previous menu of this page (' + items.length + ' links)</summary><ul></ul>';
    var ul = det.querySelector('ul'); items.forEach(function (x) { var li = d.createElement('li'), a = d.createElement('a'); a.href = x[0]; a.textContent = x[1]; li.appendChild(a); ul.appendChild(li); });
    d.body.appendChild(det);
  }
  var f = d.createElement('footer'); f.className = 'u-skin-dir'; f.setAttribute('aria-label', 'Site directory'); f.innerHTML = '<div class="dir"></div>';
  d.body.appendChild(f); try { U.nav.directory(f.querySelector('.dir')); } catch (e) {}
  U.skin = { legacyLinks: old ? old.querySelectorAll('a[href]').length : 0 };
})(window);
