/**
 * Loads split_pane.js only after the Panel app shell exists in the DOM.
 * pn.extension js_files run from <head> before Bokeh paints the toolbar, so
 * split_pane used to run too early and never update #split-status (stuck on "split: ?").
 */
(function () {
  if (window.__4dpapersSplitLoaderDone) return;
  window.__4dpapersSplitLoaderDone = true;

  var SRC = "/assets/split_pane.js?v=101";

  function markFailed(msg) {
    var el =
      document.getElementById("split-status") ||
      document.querySelector(".split-status-target");
    if (el) el.textContent = msg;
  }

  function inject() {
    if (document.querySelector("script[data-4dpapers-split-pane]")) return;
    var s = document.createElement("script");
    s.src = SRC;
    s.async = true;
    s.setAttribute("data-4dpapers-split-pane", "1");
    s.onerror = function () {
      markFailed("split: failed to load " + SRC);
    };
    document.head.appendChild(s);
  }

  function readyEnough() {
    return (
      document.body &&
      (document.querySelector(".app-shell") || document.querySelector(".body-row"))
    );
  }

  function tryInject() {
    if (readyEnough()) {
      inject();
      return true;
    }
    return false;
  }

  var n = 0;
  var t = setInterval(function () {
    n++;
    if (tryInject() || n > 200) clearInterval(t);
  }, 50);
})();
