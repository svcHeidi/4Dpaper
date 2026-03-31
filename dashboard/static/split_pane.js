// split_pane.js - v19: shadow-DOM-aware draggable gutters for 2-pane or 3-pane layouts
(function boot() {
  window.SPLIT_VERSION = 19;

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
        var hit = root.querySelector(selector);
        if (hit) {
          found = hit;
          return;
        }
      } catch (e) { }
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
      } catch (e) { }
    });
  }

  function getGutters() {
    return {
      leftCenter: deepQuerySelector("[class*='split-gutter--between-left-center']"),
      centerRight: deepQuerySelector("[class*='split-gutter--between-center-right']")
    };
  }

  function getPanes() {
    var left = deepQuerySelector(".pane-left");
    var center = deepQuerySelector(".pane-center");
    var right = deepQuerySelector(".pane-right");
    if (left === center) center = null;
    if (center === right) right = null;
    if (left === right) right = null;
    return { left: left, center: center, right: right };
  }

  function clamp(n, lo, hi) {
    return Math.max(lo, Math.min(hi, n));
  }

  function clearFixedWidth(el) {
    if (!el) return;
    el.style.removeProperty("flex");
    el.style.removeProperty("width");
    el.style.removeProperty("min-width");
    el.style.removeProperty("max-width");
  }

  function setFixedWidth(el, px) {
    if (!el) return;
    el.style.setProperty("flex", "0 0 " + px + "px", "important");
    el.style.setProperty("width", px + "px", "important");
    el.style.setProperty("min-width", px + "px", "important");
    el.style.setProperty("max-width", px + "px", "important");
  }

  function usableRowWidth(panes, gutters) {
    var first = panes.left || panes.center || panes.right;
    var last = panes.right || panes.center || panes.left;
    if (!first || !last || first === last) return 0;
    var r1 = first.getBoundingClientRect();
    var r2 = last.getBoundingClientRect();
    var count = 0;
    if (gutters.leftCenter) count++;
    if (gutters.centerRight) count++;
    return Math.max(0, (r2.right - r1.left) - (count * GUTTER_WIDTH));
  }

  function layoutFromStorage(panes, gutters) {
    var rowW = usableRowWidth(panes, gutters);
    if (!rowW) return;

    var lw = parseInt(localStorage.getItem(LS_LEFT) || "", 10);
    var rw = parseInt(localStorage.getItem(LS_RIGHT) || "", 10);
    var wantLeft = Number.isFinite(lw) ? lw : null;
    var wantRight = Number.isFinite(rw) ? rw : null;

    clearFixedWidth(panes.center);

    if (panes.left && panes.center && panes.right) {
      if (wantLeft !== null) {
        wantLeft = clamp(wantLeft, MIN_LEFT, rowW - MIN_CENTER - MIN_RIGHT);
      }
      if (wantRight !== null) {
        wantRight = clamp(wantRight, MIN_RIGHT, rowW - MIN_CENTER - MIN_LEFT);
      }
      if (wantLeft !== null && wantRight !== null) {
        var maxSum = rowW - MIN_CENTER;
        var overflow = (wantLeft + wantRight) - maxSum;
        if (overflow > 0) {
          var shrinkRight = Math.min(overflow, wantRight - MIN_RIGHT);
          wantRight -= shrinkRight;
          overflow -= shrinkRight;
          if (overflow > 0) {
            wantLeft -= Math.min(overflow, wantLeft - MIN_LEFT);
          }
        }
      }
    } else if (panes.left && panes.center && wantLeft !== null) {
      wantLeft = clamp(wantLeft, MIN_LEFT, rowW - MIN_CENTER);
    } else if (panes.center && panes.right && wantRight !== null) {
      wantRight = clamp(wantRight, MIN_RIGHT, rowW - MIN_CENTER);
    }

    if (wantLeft !== null) setFixedWidth(panes.left, wantLeft);
    if (wantRight !== null) setFixedWidth(panes.right, wantRight);
  }

  function reflow() {
    applyWrap();
    try {
      window.dispatchEvent(new Event("resize"));
    } catch (e) { }
  }

  function beginDrag(gutterEl, onMove, onEnd) {
    if (!gutterEl) return;
    gutterEl.addEventListener("mousedown", function (e) {
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      gutterEl.classList.add("__split-dragging");
      document.body.style.cursor = "ew-resize";
      document.body.style.userSelect = "none";

      var move = function (ev) { onMove(ev); };
      var up = function () {
        window.removeEventListener("mousemove", move, true);
        window.removeEventListener("mouseup", up, true);
        gutterEl.classList.remove("__split-dragging");
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        try {
          if (onEnd) onEnd();
        } catch (e2) { }
        reflow();
      };

      window.addEventListener("mousemove", move, true);
      window.addEventListener("mouseup", up, true);
    }, true);
  }

  function init() {
    if (window.__splitDone) return true;

    var gutters = getGutters();
    var panes = getPanes();
    var hasLeftPair = !!(gutters.leftCenter && panes.left && panes.center);
    var hasRightPair = !!(gutters.centerRight && panes.center && panes.right);

    if (!hasLeftPair && !hasRightPair) {
      setStatus("split: waiting layout");
      return false;
    }

    window.__splitDone = true;
    layoutFromStorage(panes, gutters);
    setStatus("split: ready v19");

    if (hasLeftPair) {
      var startXLeft = 0;
      var startLeftW = 0;
      var startRightW = 0;

      gutters.leftCenter.addEventListener("mousedown", function (e) {
        startXLeft = e.clientX;
        startLeftW = panes.left.getBoundingClientRect().width;
        startRightW = panes.right ? panes.right.getBoundingClientRect().width : 0;
      }, { capture: true });

      beginDrag(gutters.leftCenter, function (ev) {
        var rowW = usableRowWidth(panes, gutters);
        var dx = ev.clientX - startXLeft;
        var maxLeft = panes.right
          ? rowW - MIN_CENTER - Math.max(MIN_RIGHT, startRightW)
          : rowW - MIN_CENTER;
        setFixedWidth(panes.left, clamp(startLeftW + dx, MIN_LEFT, maxLeft));
      }, function () {
        localStorage.setItem(LS_LEFT, String(panes.left.getBoundingClientRect().width | 0));
      });
    }

    if (hasRightPair) {
      var startXRight = 0;
      var startPaneLeftW = 0;
      var startRightW2 = 0;

      gutters.centerRight.addEventListener("mousedown", function (e) {
        startXRight = e.clientX;
        startPaneLeftW = panes.left ? panes.left.getBoundingClientRect().width : 0;
        startRightW2 = panes.right.getBoundingClientRect().width;
      }, { capture: true });

      beginDrag(gutters.centerRight, function (ev) {
        var rowW = usableRowWidth(panes, gutters);
        var dx = ev.clientX - startXRight;
        var maxRight = panes.left
          ? rowW - MIN_CENTER - Math.max(MIN_LEFT, startPaneLeftW)
          : rowW - MIN_CENTER;
        setFixedWidth(panes.right, clamp(startRightW2 - dx, MIN_RIGHT, maxRight));
      }, function () {
        localStorage.setItem(LS_RIGHT, String(panes.right.getBoundingClientRect().width | 0));
      });
    }

    window.addEventListener("resize", reflow);
    reflow();
    return true;
  }

  function tryInit() {
    if (window.__splitDone) return true;
    return init();
  }

  setStatus("split: loading...");
  if (tryInit()) return;

  var pollN = 0;
  var poll = setInterval(function () {
    pollN++;
    if (tryInit()) {
      clearInterval(poll);
      return;
    }
    if (pollN % 10 === 0) {
      setStatus("split: waiting DOM... (" + pollN + ")");
    }
    if (pollN > 120) {
      clearInterval(poll);
      setStatus("split: failed");
    }
  }, 100);

  if (typeof MutationObserver !== "undefined") {
    try {
      var mo = new MutationObserver(function () {
        if (window.__splitDone) return;
        if (tryInit()) {
          try { clearInterval(poll); } catch (e) { }
          try { mo.disconnect(); } catch (e2) { }
        }
      });
      mo.observe(document.body, { childList: true, subtree: true });
    } catch (e) { }
  }
})();
