// activity_bar.js — config-driven panel switching for 4Dpapers dashboard
(function () {
  if (window.__4dpapersActivityBarDone) return;
  window.__4dpapersActivityBarDone = true;

  var LS_ACTIVE = "4dpapers.layout.activePanel";

  function deepQuerySelector(selector) {
    var found = null;
    function searchRoot(root) {
      if (!root || found) return;
      try {
        var hit = root.querySelector(selector);
        if (hit) { found = hit; return; }
      } catch (e) {}
      var all = root.querySelectorAll("*");
      for (var i = 0; i < all.length; i++) {
        if (all[i].shadowRoot) searchRoot(all[i].shadowRoot);
      }
    }
    searchRoot(document.documentElement);
    return found;
  }

  function switchPanel(panelId) {
    var config = window.SPLIT_CONFIG;
    if (!config || !config.panels) return;

    // Hide all panel slots
    config.panels.forEach(function (p) {
      var slot = deepQuerySelector(".panel-slot--" + p.id);
      if (slot) slot.style.setProperty("display", "none", "important");
    });

    // Show target slot
    var target = deepQuerySelector(".panel-slot--" + panelId);
    if (target) target.style.setProperty("display", "flex", "important");

    // Update active indicator on buttons
    var btns = document.querySelectorAll(".activity-bar-btn");
    btns.forEach(function (btn) {
      if (btn.dataset.panelId === panelId) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });

    localStorage.setItem(LS_ACTIVE, panelId);
  }

  // Expose for onclick handlers in Python-generated activity bar HTML
  window.__activityBarSwitch = switchPanel;

  function restoreActivePanel() {
    var config = window.SPLIT_CONFIG;
    if (!config || !config.panels) return;
    var saved = localStorage.getItem(LS_ACTIVE);
    var ids = config.panels.map(function (p) { return p.id; });
    var active = (saved && ids.indexOf(saved) !== -1) ? saved : config.defaultPanel;
    switchPanel(active);
  }

  function init() {
    var bar = document.getElementById("activity-bar");
    if (!bar) return false;
    // SPLIT_CONFIG must also be present before we restore state
    if (!window.SPLIT_CONFIG) return false;
    restoreActivePanel();
    return true;
  }

  if (init()) return;

  var pollN = 0;
  var poll = setInterval(function () {
    pollN++;
    if (init()) { clearInterval(poll); return; }
    if (pollN > 120) { clearInterval(poll); }
  }, 100);
})();
