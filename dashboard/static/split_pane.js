// split_pane.js — v17: gutters + shadow-DOM–aware queries (Panel/Bokeh nest layout in shadow roots)
(function boot() {
  window.SPLIT_VERSION = 17;

  if (window.__splitDone) return;

  var MIN_LEFT = 240;
  var MIN_CENTER = 360;
  var MIN_RIGHT = 360;
  /** Two gutters × 8px — must match dashboard/app.py _split_gutter width */
  var GUTTER_TOTAL = 16;

  var LS_LEFT = "4dpapers.pane.leftWidth";
  var LS_RIGHT = "4dpapers.pane.rightWidth";

  /** querySelector across open shadow roots (Bokeh 3 / Panel nest layout in shadow). */
  function deepQuerySelector(selector) {
    var found = null;
    function searchRoot(root) {
      if (!root || found) return;
      try {
        var h = root.querySelector(selector);
        if (h) {
          found = h;
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
      if (el) {
        el.textContent = text;
        return true;
      }
      return false;
    }
    if (apply()) return;
    var tries = 0;
    var id = setInterval(function () {
      tries++;
      if (apply() || tries > 200) clearInterval(id);
    }, 50);
  }

  setStatus("split: loading…");

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

  function getGutters() {
    var gLC = deepQuerySelector("[class*='split-gutter--between-left-center']");
    var gCR = deepQuerySelector("[class*='split-gutter--between-center-right']");
    if (!gLC || !gCR) return null;
    return { leftCenter: gLC, centerRight: gCR };
  }

  function getPanes() {
    var leftKid = deepQuerySelector(".pane-left");
    var centerKid = deepQuerySelector(".pane-center");
    var rightKid = deepQuerySelector(".pane-right");
    if (!leftKid || !centerKid || !rightKid) return null;
    if (leftKid === centerKid || centerKid === rightKid || leftKid === rightKid) return null;
    return { left: leftKid, center: centerKid, right: rightKid };
  }

  function clamp(n, lo, hi) {
    return Math.max(lo, Math.min(hi, n));
  }

  function usableRowWidth(panes) {
    var rowW = 0;
    if (panes && panes.left && panes.right) {
      var l = panes.left.getBoundingClientRect();
      var r = panes.right.getBoundingClientRect();
      rowW = r.right - l.left;
    }
    if (rowW < 10) {
      var g1 = deepQuerySelector("[class*='split-gutter--between-left-center']");
      var g2 = deepQuerySelector("[class*='split-gutter--between-center-right']");
      if (g1 && g2) {
        rowW = g2.getBoundingClientRect().right - g1.getBoundingClientRect().left;
      }
    }
    return Math.max(0, rowW - GUTTER_TOTAL);
  }

  function setFixedWidth(el, px) {
    el.style.setProperty("flex", "0 0 " + px + "px", "important");
    el.style.setProperty("width", px + "px", "important");
    el.style.setProperty("min-width", px + "px", "important");
    el.style.setProperty("max-width", px + "px", "important");
  }

  function clearFixedWidth(el) {
    el.style.removeProperty("flex");
    el.style.removeProperty("width");
    el.style.removeProperty("min-width");
    el.style.removeProperty("max-width");
  }

  function layoutFromStorage(panes) {
    var rowW = usableRowWidth(panes);
    if (!rowW || rowW < (MIN_LEFT + MIN_CENTER + MIN_RIGHT)) return;

    var lw = parseInt(localStorage.getItem(LS_LEFT) || "", 10);
    var rw = parseInt(localStorage.getItem(LS_RIGHT) || "", 10);

    var wantLeft = Number.isFinite(lw) ? lw : null;
    var wantRight = Number.isFinite(rw) ? rw : null;

    if (wantLeft !== null) {
      var maxLeft = rowW - MIN_CENTER - MIN_RIGHT;
      wantLeft = clamp(wantLeft, MIN_LEFT, maxLeft);
    }
    if (wantRight !== null) {
      var maxRight = rowW - MIN_CENTER - MIN_LEFT;
      wantRight = clamp(wantRight, MIN_RIGHT, maxRight);
    }

    if (wantLeft !== null && wantRight !== null) {
      var maxSum = rowW - MIN_CENTER;
      var overflow = (wantLeft + wantRight) - maxSum;
      if (overflow > 0) {
        var shrinkR = Math.min(overflow, wantRight - MIN_RIGHT);
        wantRight -= shrinkR;
        overflow -= shrinkR;
        if (overflow > 0) {
          var shrinkL = Math.min(overflow, wantLeft - MIN_LEFT);
          wantLeft -= shrinkL;
          overflow -= shrinkL;
        }
      }
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

  function init() {
    if (window.__splitDone) return true;

    var gutters = getGutters();
    if (!gutters) {
      setStatus("split: waiting gutters");
      return false;
    }

    var panes = getPanes();
    if (!panes) {
      setStatus("split: waiting panes");
      return false;
    }

    window.__splitDone = true;
    var rL0 = panes.left.getBoundingClientRect();
    var rR0 = panes.right.getBoundingClientRect();
    setStatus(
      "split: ok v17 | drag gutters (L=" +
      Math.round(rL0.width) + " R=" + Math.round(rR0.width) + ")"
    );

    clearFixedWidth(panes.center);
    try {
      layoutFromStorage(panes);
    } catch (e) { }

    function beginDrag(gutterEl, onMove, onEnd) {
      gutterEl.addEventListener(
        "mousedown",
        function (e) {
          if (e.button !== 0) return;
          e.preventDefault();
          e.stopPropagation();
          gutterEl.classList.add("__split-dragging");
          document.body.style.cursor = "ew-resize";
          document.body.style.userSelect = "none";

          var move = function (ev) {
            onMove(ev);
          };
          var up = function () {
            window.removeEventListener("mousemove", move, true);
            window.removeEventListener("mouseup", up, true);
            gutterEl.classList.remove("__split-dragging");
            document.body.style.cursor = "";
            document.body.style.userSelect = "";
            try {
              onEnd();
            } catch (x) { }
            reflow();
          };

          window.addEventListener("mousemove", move, true);
          window.addEventListener("mouseup", up, true);
        },
        true
      );
    }

    // Left gutter: left <-> center
    (function () {
      var startX = 0;
      var startLeftW = 0;
      var startRightW = 0;
      beginDrag(
        gutters.leftCenter,
        function (ev) {
          var rowW = usableRowWidth(panes);
          var dx = ev.clientX - startX;
          var proposed = startLeftW + dx;
          var maxLeft = rowW - MIN_CENTER - Math.max(MIN_RIGHT, startRightW);
          var lw = clamp(proposed, MIN_LEFT, maxLeft);
          setFixedWidth(panes.left, lw);
        },
        function () {
          localStorage.setItem(LS_LEFT, String(panes.left.getBoundingClientRect().width | 0));
        }
      );
      gutters.leftCenter.addEventListener(
        "mousedown",
        function (e) {
          startX = e.clientX;
          startLeftW = panes.left.getBoundingClientRect().width;
          startRightW = panes.right.getBoundingClientRect().width;
        },
        { capture: true }
      );
    })();

    // Right gutter: center <-> right
    (function () {
      var startX = 0;
      var startLeftW = 0;
      var startRightW = 0;
      beginDrag(
        gutters.centerRight,
        function (ev) {
          var rowW = usableRowWidth(panes);
          var dx = ev.clientX - startX;
          var proposed = startRightW - dx;
          var maxRight = rowW - MIN_CENTER - Math.max(MIN_LEFT, startLeftW);
          var rw = clamp(proposed, MIN_RIGHT, maxRight);
          setFixedWidth(panes.right, rw);
        },
        function () {
          localStorage.setItem(LS_RIGHT, String(panes.right.getBoundingClientRect().width | 0));
        }
      );
      gutters.centerRight.addEventListener(
        "mousedown",
        function (e) {
          startX = e.clientX;
          startLeftW = panes.left.getBoundingClientRect().width;
          startRightW = panes.right.getBoundingClientRect().width;
        },
        { capture: true }
      );
    })();

    window.addEventListener("resize", reflow);

    reflow();
    return true;
  }

  function tryInit() {
    if (window.__splitDone) return true;
    return init();
  }

  if (tryInit()) return;

  var pollN = 0;
  var poll = setInterval(function () {
    pollN++;
    if (tryInit()) {
      clearInterval(poll);
      return;
    }
    if (pollN % 10 === 0) {
      setStatus("split: waiting DOM… (" + pollN + ")");
    }
    if (pollN > 120) {
      clearInterval(poll);
      setStatus("split: failed — see console [SPLIT]");
    }
  }, 100);

  if (typeof MutationObserver !== "undefined") {
    try {
      var mo = new MutationObserver(function () {
        if (window.__splitDone) return;
        if (tryInit()) {
          try {
            clearInterval(poll);
          } catch (e) { }
          try {
            mo.disconnect();
          } catch (e2) { }
        }
      });
      mo.observe(document.body, { childList: true, subtree: true });
    } catch (e) { }
  }
})();
