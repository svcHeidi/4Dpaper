// split_pane.js - v23: simplified gutter handlers with reusable logic
(function boot() {
  window.SPLIT_VERSION = 23;

  if (window.__splitDone) return;

  var LS_MAIN = "4dpapers.pane.mainWidth";
  var LS_EXPLORER = "4dpapers.pane.explorerWidth";
  var MIN_MAIN = 200;
  var MIN_PREVIEW = 320;
  var MIN_EXPLORER = 120;
  var GUTTER_WIDTH = 8;

  // ============ DOM Helpers ============
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

  // ============ Sizing Helpers ============
  function clamp(n, lo, hi) { return Math.max(lo, Math.min(hi, n)); }

  function setElementWidth(el, px) {
    if (!el) return;
    el.style.setProperty("flex", "0 0 " + px + "px", "important");
    el.style.setProperty("width", px + "px", "important");
    el.style.setProperty("min-width", px + "px", "important");
    el.style.setProperty("max-width", px + "px", "important");
  }

  function clearElementWidth(el) {
    if (!el) return;
    el.style.removeProperty("flex");
    el.style.removeProperty("width");
    el.style.removeProperty("min-width");
    el.style.removeProperty("max-width");
  }

  function setElementGrow(el) {
    if (!el) return;
    el.style.setProperty("flex", "1 1 0", "important");
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

  var _reflowing = false;
  function reflow() {
    if (_reflowing) return;
    _reflowing = true;
    applyWrap();
    try { window.dispatchEvent(new Event("resize")); } catch (e) {}
    _reflowing = false;
  }

  // ============ Panel-Aware Gutter Handler ============
  // Generic handler for any gutter between two panels
  // Grows first panel, shrinks second panel while respecting minimums
  function attachGutterHandler(config) {
    var gutter = config.gutter;
    var firstPanel = config.firstPanel;
    var secondPanel = config.secondPanel;
    var minFirst = config.minFirst;
    var minSecond = config.minSecond;
    var storageKey = config.storageKey;
    var growSecond = config.growSecond;  // If true, second panel grows to fill space after resize

    if (!gutter || !firstPanel || !secondPanel) return;

    var startX = 0, startFirstW = 0, startSecondW = 0;

    gutter.addEventListener("mousedown", function (e) {
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();

      startX = e.clientX;
      startFirstW = firstPanel.getBoundingClientRect().width;
      startSecondW = secondPanel.getBoundingClientRect().width;

      gutter.classList.add("__split-dragging");
      document.body.style.cursor = "ew-resize";
      document.body.style.userSelect = "none";

      function onMove(ev) {
        var dx = ev.clientX - startX;
        // How much can second panel shrink?
        var secondShrinkSpace = startSecondW - minSecond;
        // First can only grow up to available shrink space
        var newFirstW = clamp(startFirstW + dx, minFirst, startFirstW + secondShrinkSpace);
        var actualChange = newFirstW - startFirstW;
        var newSecondW = startSecondW - actualChange;

        setElementWidth(firstPanel, newFirstW);
        setElementWidth(secondPanel, newSecondW);
      }

      function onUp() {
        window.removeEventListener("mousemove", onMove, true);
        window.removeEventListener("mouseup", onUp, true);
        gutter.classList.remove("__split-dragging");
        document.body.style.cursor = "";
        document.body.style.userSelect = "";

        if (storageKey) {
          var finalWidth = firstPanel.getBoundingClientRect().width | 0;
          localStorage.setItem(storageKey, String(finalWidth));
        }

        if (growSecond) {
          setElementGrow(secondPanel);
        }

        reflow();
      }

      window.addEventListener("mousemove", onMove, true);
      window.addEventListener("mouseup", onUp, true);
    }, true);
  }

  // ============ Layout Restoration ============
  function restoreLayout(els) {
    // Restore main panel width (preview grows to fill rest)
    var rowW = Math.max(0, (els.preview.getBoundingClientRect().right - els.main.getBoundingClientRect().left) - GUTTER_WIDTH);
    if (rowW) {
      var saved = parseInt(localStorage.getItem(LS_MAIN) || "", 10);
      if (Number.isFinite(saved)) {
        var w = clamp(saved, MIN_MAIN, rowW - MIN_PREVIEW);
        setElementWidth(els.main, w);
        setElementGrow(els.preview);  // Make preview grow to fill remaining space
      }
    }

    // Restore explorer width
    var saved = parseInt(localStorage.getItem(LS_EXPLORER) || "", 10);
    if (Number.isFinite(saved) && els.explorer) {
      var w = Math.max(MIN_EXPLORER, saved);
      setElementWidth(els.explorer, w);
    }
  }

  // ============ Explorer Collapse ============
  function setupExplorerCollapse() {
    var btn = deepQuerySelector("#explorer-collapse-btn");
    var explorer = deepQuerySelector(".explorer-sidebar-wrap");
    if (!btn || !explorer) return;

    window.__explorerCollapseToggle = function () {
      var collapsed = explorer.getAttribute("data-collapsed") === "1";
      if (collapsed) {
        // Restore
        var w = parseInt(explorer.getAttribute("data-prev-width") || "248", 10);
        setElementWidth(explorer, w);
        explorer.setAttribute("data-collapsed", "0");
        btn.textContent = "\u2039";
        btn.style.setProperty("width", "24px", "important");
        btn.style.setProperty("flex", "0 0 24px", "important");
      } else {
        // Collapse
        explorer.setAttribute("data-prev-width", explorer.getBoundingClientRect().width | 0);
        setElementWidth(explorer, 20);
        explorer.setAttribute("data-collapsed", "1");
        btn.textContent = "\u203a";
        btn.style.setProperty("width", "20px", "important");
        btn.style.setProperty("flex", "0 0 20px", "important");
      }
      reflow();
    };
  }

  // ============ Initialization ============
  function getElements() {
    var cfg = window.SPLIT_CONFIG || {};
    return {
      explorer: deepQuerySelector(cfg.explorerSelector || ".explorer-sidebar-wrap"),
      main:     deepQuerySelector(cfg.mainPanelSelector || ".main-panel"),
      preview:  deepQuerySelector(cfg.previewPanelSelector || ".pane-right"),
      gutterEM: deepQuerySelector(cfg.gutterExplorerMainSelector || "[class*='split-gutter--between-explorer-editor']"),
      gutterMP: deepQuerySelector(cfg.gutterMainPreviewSelector || "[class*='split-gutter--between-main-preview']"),
    };
  }

  function init() {
    if (window.__splitDone) return true;

    var els = getElements();
    if (!els.main || !els.preview) {
      setStatus("split: waiting layout");
      return false;
    }

    window.__splitDone = true;

    // Setup both gutters with unified handler
    if (els.gutterEM) {
      attachGutterHandler({
        gutter: els.gutterEM,
        firstPanel: els.explorer,
        secondPanel: els.main,
        minFirst: MIN_EXPLORER,
        minSecond: MIN_MAIN,
        storageKey: LS_EXPLORER,
        growSecond: false,
      });
    }

    if (els.gutterMP) {
      attachGutterHandler({
        gutter: els.gutterMP,
        firstPanel: els.main,
        secondPanel: els.preview,
        minFirst: MIN_MAIN,
        minSecond: MIN_PREVIEW,
        storageKey: LS_MAIN,
        growSecond: true,  // Preview panel grows to fill remaining space
      });
    }

    // Restore saved sizes and setup collapse
    restoreLayout(els);
    setupExplorerCollapse();

    window.addEventListener("resize", reflow);
    reflow();
    setStatus("split: ready v23");
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
