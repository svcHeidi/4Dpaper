/**
 * Loads split_pane.js only after the Panel app shell exists in the DOM.
 * pn.extension js_files run from <head> before Bokeh paints the toolbar, so
 * split_pane used to run too early and never update #split-status.
 */
(function () {
  if (window.__4dpapersSplitLoaderDone) return;
  window.__4dpapersSplitLoaderDone = true;

  var SRC = "/assets/split_pane.js?v=102";

  function markFailed(msg) {
    var el =
      document.getElementById("split-status") ||
      document.querySelector(".split-status-target");
    if (el) el.textContent = msg;
  }

  function inject() {
    if (document.querySelector("script[data-4dpapers-split-pane]")) return;
    var script = document.createElement("script");
    script.src = SRC;
    script.async = true;
    script.setAttribute("data-4dpapers-split-pane", "1");
    script.onerror = function () {
      markFailed("split: failed to load " + SRC);
    };
    document.head.appendChild(script);
  }

  function readyEnough() {
    return (
      document.body &&
      (document.querySelector(".app-shell") || document.querySelector(".body-row"))
    );
  }

  function tryInject() {
    if (!readyEnough()) return false;
    inject();
    return true;
  }

  var tries = 0;
  var timer = setInterval(function () {
    tries++;
    if (tryInject() || tries > 200) clearInterval(timer);
  }, 50);
})();
