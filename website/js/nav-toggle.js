/* SOST shared top-nav toggle.
   Auto-injects a pulsing red/gold "HIDE NAV / SHOW NAV" button into
   every page that has a <nav> element, and wires up a sessionStorage-
   backed collapsed state shared across pages.
   Compatible with the existing index.html implementation: when a button
   with id="navToggleBtn" already exists, the script only attaches its
   visual styling and lets the in-page handler do the toggling. */
(function () {
  "use strict";

  // Pre-paint flicker fix: if the previous page collapsed the nav,
  // toggle the html-level marker before the first paint so the nav
  // renders collapsed from frame 0.
  try {
    if (sessionStorage.getItem("sost_nav_collapsed") === "1") {
      document.documentElement.classList.add("pre-nav-collapsed");
    }
  } catch (e) { /* ignore */ }

  // Inject the shared CSS exactly once.
  if (!document.getElementById("sost-nav-toggle-style")) {
    var style = document.createElement("style");
    style.id = "sost-nav-toggle-style";
    style.textContent = [
      ".sost-nav-toggle, .nav-toggle {",
      "  position: relative;",
      "  background: linear-gradient(135deg, rgba(251,1,13,0.22), rgba(245,158,11,0.14) 65%, rgba(34,211,238,0.10));",
      "  border: 1px solid rgba(251,1,13,0.65);",
      "  color: #fff5f5;",
      "  font-family: 'JetBrains Mono', ui-monospace, monospace;",
      "  font-size: 11px;",
      "  font-weight: 700;",
      "  letter-spacing: 1.6px;",
      "  padding: 7px 14px;",
      "  border-radius: 6px;",
      "  cursor: pointer;",
      "  flex: 0 0 auto;",
      "  transition: transform .18s ease, color .18s ease, border-color .2s ease;",
      "  box-shadow: 0 0 8px rgba(251,1,13,0.42), 0 0 18px rgba(245,158,11,0.22);",
      "  text-shadow: 0 0 6px rgba(251,1,13,0.55);",
      "  animation: sostNavPulse 2.4s ease-in-out infinite;",
      "  -webkit-tap-highlight-color: transparent;",
      "}",
      ".sost-nav-toggle:hover, .nav-toggle:hover {",
      "  color: #ffffff;",
      "  border-color: rgba(255,200,87,0.95);",
      "  transform: translateY(-1px);",
      "}",
      ".sost-nav-toggle:focus-visible, .nav-toggle:focus-visible {",
      "  outline: none;",
      "  border-color: rgba(34,211,238,0.95);",
      "  box-shadow: 0 0 14px rgba(34,211,238,0.7), 0 0 28px rgba(34,211,238,0.35);",
      "}",
      "@keyframes sostNavPulse {",
      "  0%, 100% {",
      "    box-shadow: 0 0 8px rgba(251,1,13,0.42),",
      "                0 0 18px rgba(245,158,11,0.22);",
      "  }",
      "  50% {",
      "    box-shadow: 0 0 16px rgba(251,1,13,0.85),",
      "                0 0 30px rgba(245,158,11,0.5),",
      "                0 0 48px rgba(251,1,13,0.28);",
      "  }",
      "}",
      "body.nav-collapsed nav { padding: 4px 0 !important; }",
      "body.nav-collapsed nav .nav-logo,",
      "body.nav-collapsed nav .nav-links,",
      "body.nav-collapsed nav .nav-hamburger,",
      "body.nav-collapsed nav a[href=\"casert-spec.html\"],",
      "body.nav-collapsed nav a[href=\"sost-dex.html\"] {",
      "  display: none !important;",
      "}",
      "body.nav-collapsed nav .container {",
      "  justify-content: flex-end !important;",
      "}",
      "html.pre-nav-collapsed body.nav-collapsed nav { padding: 4px 0 !important; }",
    ].join("\n");
    (document.head || document.documentElement).appendChild(style);
  }

  function applyState(collapsed) {
    document.body.classList.toggle("nav-collapsed", collapsed);
    var btns = document.querySelectorAll(".sost-nav-toggle, #navToggleBtn");
    btns.forEach(function (b) {
      b.textContent = collapsed ? "▼ SHOW NAV" : "▲ HIDE NAV";
      b.setAttribute("aria-pressed", collapsed ? "true" : "false");
    });
    try {
      sessionStorage.setItem("sost_nav_collapsed", collapsed ? "1" : "0");
    } catch (e) { /* ignore */ }
  }

  function toggleHandler(ev) {
    if (ev) ev.preventDefault();
    applyState(!document.body.classList.contains("nav-collapsed"));
  }

  // Expose a global so existing inline onclick="toggleNav()" handlers
  // (e.g. the one in index.html) keep working.
  window.toggleNav = function () { toggleHandler(); };

  function init() {
    var collapsed = false;
    try { collapsed = sessionStorage.getItem("sost_nav_collapsed") === "1"; }
    catch (e) { /* ignore */ }
    var nav = document.querySelector("nav");
    if (!nav) {
      // No nav on this page — still apply the state so a future inject
      // is consistent.
      if (collapsed) document.body.classList.add("nav-collapsed");
      return;
    }
    var existing = nav.querySelector("#navToggleBtn, .sost-nav-toggle");
    if (!existing) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "sost-nav-toggle";
      btn.id = "navToggleBtn";
      btn.title = "Hide / show the top navigation";
      btn.textContent = collapsed ? "▼ SHOW NAV" : "▲ HIDE NAV";
      btn.addEventListener("click", toggleHandler);
      // Insert just before the hamburger so it lands next to the nav
      // controls in the same flex row. Fall back to appending into the
      // .container if the structure differs.
      var hamburger = nav.querySelector(".nav-hamburger");
      var container = nav.querySelector(".container") || nav;
      if (hamburger && hamburger.parentNode === container) {
        container.insertBefore(btn, hamburger);
      } else {
        container.appendChild(btn);
      }
    } else if (!existing.dataset.sostBound) {
      // Existing index.html button: keep its inline onclick but make
      // sure we react to history-restored collapsed states too.
      existing.dataset.sostBound = "1";
    }
    applyState(collapsed);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
