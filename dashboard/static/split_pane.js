// split_pane.js - v20: 2-pane layout, reads config from window.SPLIT_CONFIG
(function boot() {
  window.SPLIT_VERSION = 20;

  if (window.__splitDone) return;

  var LS_MAIN = "4dpapers.pane.mainWidth";
  var MIN_MAIN = 200;
  var MIN_PREVIEW = 320;
  var GUTTER_WIDTH = 8;

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

  function findStatusEl() {
    return (
      document.getElementById("split-status") ||
      document.querySelector(".split-status-target") ||
      deepQuerySelector("#split-status") ||
      deepQuerySelector(".split-status-target") ||
      deepQuerySelector("[data-split-status]")
    );
  }

  function setStatus(text) {
    function apply() {
      var el = findStatusEl();
      if (!el) return false;
      el.textContent = text;
      return true;
    }
    if (apply()) return;
    var tries = 0;
    var id = setInterval(function () {
      tries++;
      if (apply() || tries > 200) clearInterval(id);
    }, 50);
  }

  function applyWrap() {
    if (typeof ace === "undefined") return;
    document.querySelectorAll(".ace_editor").forEach(function (el) {
      try {
        var editor = ace.edit(el);
        editor.session.setUseWrapMode(true);
        editor.resize();
      } catch (e) {}
    });
  }

  function clamp(n, lo, hi) { return Math.max(lo, Math.min(hi, n)); }

  function setFixedWidth(el, px) {
    if (!el) return;
    el.style.setProperty("flex", "0 0 " + px + "px", "important");
    el.style.setProperty("width", px + "px", "important");
    el.style.setProperty("min-width", px + "px", "important");
    el.style.setProperty("max-width", px + "px", "important");
  }

  function clearFixedWidth(el) {
    if (!el) return;
    el.style.removeProperty("flex");
    el.style.removeProperty("width");
    el.style.removeProperty("min-width");
    el.style.removeProperty("max-width");
  }

  function reflow() {
    applyWrap();
    try { window.dispatchEvent(new Event("resize")); } catch (e) {}
  }

  function usableWidth(mainEl, previewEl) {
    var r1 = mainEl.getBoundingClientRect();
    var r2 = previewEl.getBoundingClientRect();
    return Math.max(0, (r2.right - r1.left) - GUTTER_WIDTH);
  }

  function getElements() {
    var cfg = window.SPLIT_CONFIG || {};
    var gutterSel  = cfg.gutterSelector       || "[class*='split-gutter--between-main-preview']";
    var mainSel    = cfg.mainPanelSelector     || ".main-panel";
    var previewSel = cfg.previewPanelSelector  || ".pane-right";
    return {
      gutter:  deepQuerySelector(gutterSel),
      main:    deepQuerySelector(mainSel),
      preview: deepQuerySelector(previewSel),
    };
  }

  function layoutFromStorage(els) {
    var rowW = usableWidth(els.main, els.preview);
    if (!rowW) return;
    var saved = parseInt(localStorage.getItem(LS_MAIN) || "", 10);
    if (!Number.isFinite(saved)) return;
    var w = clamp(saved, MIN_MAIN, rowW - MIN_PREVIEW);
    clearFixedWidth(els.preview);
    setFixedWidth(els.main, w);
  }

  function init() {
    if (window.__splitDone) return true;

    var els = getElements();
    if (!els.gutter || !els.main || !els.preview) {
      setStatus("split: waiting layout");
      return false;
    }

    window.__splitDone = true;
    layoutFromStorage(els);
    setStatus("split: ready v20");

    var startX = 0;
    var startMainW = 0;

    els.gutter.addEventListener("mousedown", function (e) {
      startX = e.clientX;
      startMainW = els.main.getBoundingClientRect().width;
    }, { capture: true });

    els.gutter.addEventListener("mousedown", function (e) {
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      els.gutter.classList.add("__split-dragging");
      document.body.style.cursor = "ew-resize";
      document.body.style.userSelect = "none";

      function onMove(ev) {
        var rowW = usableWidth(els.main, els.preview);
        var dx = ev.clientX - startX;
        setFixedWidth(els.main, clamp(startMainW + dx, MIN_MAIN, rowW - MIN_PREVIEW));
      }
      function onUp() {
        window.removeEventListener("mousemove", onMove, true);
        window.removeEventListener("mouseup", onUp, true);
        els.gutter.classList.remove("__split-dragging");
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        localStorage.setItem(LS_MAIN, String(els.main.getBoundingClientRect().width | 0));
        reflow();
      }
      window.addEventListener("mousemove", onMove, true);
      window.addEventListener("mouseup", onUp, true);
    }, true);

    window.addEventListener("resize", reflow);
    reflow();
    return true;
  }

  setStatus("split: loading...");
  if (init()) return;

  var pollN = 0;
  var poll = setInterval(function () {
    pollN++;
    if (init()) { clearInterval(poll); return; }
    if (pollN % 10 === 0) setStatus("split: waiting DOM... (" + pollN + ")");
    if (pollN > 120) { clearInterval(poll); setStatus("split: failed"); }
  }, 100);

  if (typeof MutationObserver !== "undefined") {
    try {
      var mo = new MutationObserver(function () {
        if (window.__splitDone) return;
        if (init()) {
          try { clearInterval(poll); } catch (e) {}
          try { mo.disconnect(); } catch (e2) {}
        }
      });
      mo.observe(document.body, { childList: true, subtree: true });
    } catch (e) {}
  }
})();
