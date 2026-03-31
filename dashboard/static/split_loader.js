/**
 * Loads split_pane.js and activity_bar.js only after the Panel app shell
 * exists in the DOM. pn.extension js_files run from <head> before Bokeh
 * paints the toolbar, so scripts used to run too early.
 */
(function () {
  if (window.__4dpapersSplitLoaderDone) return;
  window.__4dpapersSplitLoaderDone = true;

  var SPLIT_SRC = "/assets/split_pane.js?v=103";
  var ACTIVITY_SRC = "/assets/activity_bar.js?v=103";

  function markFailed(msg) {
    var el =
      document.getElementById("split-status") ||
      document.querySelector(".split-status-target");
    if (el) el.textContent = msg;
  }

  function injectScript(src, attr) {
    if (document.querySelector('script[' + attr + ']')) return;
    var script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.setAttribute(attr, "1");
    script.onerror = function () { markFailed("failed to load " + src); };
    document.head.appendChild(script);
  }

  function inject() {
    injectScript(SPLIT_SRC, "data-4dpapers-split-pane");
    injectScript(ACTIVITY_SRC, "data-4dpapers-activity-bar");
  }

  function readyEnough() {
    return (
      document.body &&
      (document.querySelector(".app-shell") || document.querySelector(".body-row"))
    );
  }

  var tries = 0;
  var timer = setInterval(function () {
    tries++;
    if (readyEnough() || tries > 200) {
      clearInterval(timer);
      inject();
    }
  }, 50);
})();
