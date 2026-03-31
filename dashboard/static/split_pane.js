// split_pane.js — v18: flexible 2-pane or 3-pane support
(function boot() {
  window.SPLIT_VERSION = 18;
  if (window.__splitDone) return;

  var MIN_LEFT = 240;
  var MIN_CENTER = 360;
  var MIN_RIGHT = 360;
  var GUTTER_WIDTH = 8;

  var LS_LEFT = "4dpapers.pane.leftWidth";
  var LS_RIGHT = "4dpapers.pane.rightWidth";

  function deepQuerySelector(selector) {
    var found = null;
    function searchRoot(root) {
      if (!root || found) return;
      try {
        var h = root.querySelector(selector);
        if (h) { found = h; return; }
      } catch (e) { }
      var all = root.querySelectorAll("*");
      for (var i = 0; i < all.length; i++) {
        if (all[i].shadowRoot) searchRoot(all[i].shadowRoot);
      }
    }
    searchRoot(document.documentElement);
    return found;
  }

  function setStatus(text) {
    var el = document.getElementById("split-status") || deepQuerySelector("#split-status");
    if (el) el.textContent = text;
    else {
      var tries = 0;
      var id = setInterval(function () {
        tries++;
        var el2 = document.getElementById("split-status") || deepQuerySelector("#split-status");
        if (el2) { el2.textContent = text; clearInterval(id); }
        else if (tries > 50) clearInterval(id);
      }, 100);
    }
  }

  setStatus("split: v18 loading…");

  function getGutters() {
    return {
      leftCenter: deepQuerySelector("[class*='split-gutter--between-left-center']"),
      centerRight: deepQuerySelector("[class*='split-gutter--between-center-right']")
    };
  }

  function getPanes() {
    return {
      left: deepQuerySelector(".pane-left"),
      center: deepQuerySelector(".pane-center"),
      right: deepQuerySelector(".pane-right")
    };
  }

  function clamp(n, lo, hi) { return Math.max(lo, Math.min(hi, n)); }

  function usableRowWidth(panes) {
    var first = panes.left || panes.center;
    var last = panes.right || panes.center || panes.left;
    if (!first || !last) return 0;
    var r1 = first.getBoundingClientRect();
    var r2 = last.getBoundingClientRect();
    var w = r2.right - r1.left;
    var gCount = (getGutters().leftCenter ? 1 : 0) + (getGutters().centerRight ? 1 : 0);
    return Math.max(0, w - (gCount * GUTTER_WIDTH));
  }

  function setFixedWidth(el, px) {
    if (!el) return;
    el.style.setProperty("flex", "0 0 " + px + "px", "important");
    el.style.setProperty("width", px + "px", "important");
    el.style.setProperty("min-width", px + "px", "important");
    el.style.setProperty("max-width", px + "px", "important");
  }

  function applyWrap() {
    if (typeof ace === "undefined") return;
    document.querySelectorAll(".ace_editor").forEach(function (el) {
      try {
        var e = ace.edit(el);
        e.session.setUseWrapMode(true);
        e.resize();
      } catch (x) { }
    });
  }

  function reflow() {
    applyWrap();
    try { window.dispatchEvent(new Event("resize")); } catch (e) { }
  }

  function init() {
    var g = getGutters();
    var p = getPanes();
    if (!p.left && !p.center) return false;
    if (!g.leftCenter && !g.centerRight) return false;

    window.__splitDone = true;
    setStatus("split: v18 active");

    function beginDrag(gutterEl, onMove, onEnd) {
      if (!gutterEl) return;
      gutterEl.addEventListener("mousedown", function (e) {
        if (e.button !== 0) return;
        e.preventDefault(); e.stopPropagation();
        gutterEl.classList.add("__split-dragging");
        document.body.style.cursor = "ew-resize";
        var move = function (ev) { onMove(ev); };
        var up = function () {
          window.removeEventListener("mousemove", move, true);
          window.removeEventListener("mouseup", up, true);
          gutterEl.classList.remove("__split-dragging");
          document.body.style.cursor = "";
          if (onEnd) onEnd();
          reflow();
        };
        window.addEventListener("mousemove", move, true);
        window.addEventListener("mouseup", up, true);
      }, true);
    }

    // Left-Center Gutter
    if (g.leftCenter && p.left && p.center) {
      var startX, startW;
      g.leftCenter.addEventListener("mousedown", function(e){
        startX = e.clientX; startW = p.left.getBoundingClientRect().width;
      }, true);
      beginDrag(g.leftCenter, function(ev) {
        var dx = ev.clientX - startX;
        var rowW = usableRowWidth(p);
        var maxL = rowW - (p.right ? MIN_RIGHT + MIN_CENTER : MIN_CENTER);
        setFixedWidth(p.left, clamp(startW + dx, MIN_LEFT, maxL));
      }, function() {
        localStorage.setItem(LS_LEFT, String(p.left.getBoundingClientRect().width | 0));
      });
    }

    // Center-Right Gutter
    if (g.centerRight && p.center && p.right) {
      var startX2, startW2;
      g.centerRight.addEventListener("mousedown", function(e){
        startX2 = e.clientX; startW2 = p.right.getBoundingClientRect().width;
      }, true);
      beginDrag(g.centerRight, function(ev) {
        var dx = ev.clientX - startX2;
        var rowW = usableRowWidth(p);
        var maxR = rowW - MIN_CENTER - (p.left ? MIN_LEFT : 0);
        setFixedWidth(p.right, clamp(startW2 - dx, MIN_RIGHT, maxR));
      }, function() {
        localStorage.setItem(LS_RIGHT, String(p.right.getBoundingClientRect().width | 0));
      });
    }

    window.addEventListener("resize", reflow);
    reflow();
    return true;
  }

  var n = 0;
  var id = setInterval(function(){
    n++;
    if (init() || n > 100) clearInterval(id);
  }, 100);
})();
