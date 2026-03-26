/**
 * 4DPaper camera overlay — loaded by the Panel app (top-level page).
 *
 * Listens for postMessages that bubble up through the iframe chain:
 *   video iframe → paper HTML relay → Panel page (here)
 *
 * Handles:
 *   4dpaper-open-camera  — show the vtk.js preview overlay
 *   4dpaper-camera       — save camera JSON via fetch (from preview iframe)
 *   4dpaper-camera-ack   — forward ack back to preview iframe (badge display)
 */
(function () {
  var overlay = null;
  var previewFrame = null;

  function buildOverlay() {
    var ov = document.createElement("div");
    ov.id = "fourd-cam-overlay";
    ov.style.cssText = (
      "position:fixed;inset:0;z-index:999999;" +
      "background:rgba(0,0,0,0.85);" +
      "display:flex;align-items:center;justify-content:center;" +
      "padding:24px;box-sizing:border-box;"
    );

    var inner = document.createElement("div");
    inner.style.cssText = (
      "width:100%;max-width:1200px;height:100%;" +
      "display:flex;flex-direction:column;" +
      "background:#1a1a2e;border-radius:8px;padding:12px;" +
      "box-sizing:border-box;box-shadow:0 8px 32px rgba(0,0,0,0.6);"
    );

    var hdr = document.createElement("div");
    hdr.style.cssText = (
      "display:flex;justify-content:space-between;align-items:center;" +
      "margin-bottom:6px;flex-shrink:0;"
    );

    var txt = document.createElement("span");
    txt.style.cssText = "color:#ccc;font-size:12px;font-family:monospace;";
    txt.innerHTML = (
      "\uD83D\uDCF7 Rotate to set camera \u2014 " +
      "syncs automatically on mouse release \u2014 " +
      "then click <b>Rebuild HTML</b>"
    );

    var closeBtn = document.createElement("button");
    closeBtn.innerHTML = "\u2715";
    closeBtn.style.cssText = (
      "background:none;border:none;color:#999;font-size:20px;" +
      "cursor:pointer;padding:0 4px;flex-shrink:0;"
    );
    closeBtn.onclick = function () { ov.style.display = "none"; };

    hdr.appendChild(txt);
    hdr.appendChild(closeBtn);

    var fr = document.createElement("iframe");
    fr.id = "fourd-cam-iframe";
    fr.frameBorder = "0";
    fr.style.cssText = (
      "flex:1;min-height:0;width:100%;border:none;border-radius:4px;display:block;"
    );

    var ftr = document.createElement("p");
    ftr.id = "fourd-cam-figid";
    ftr.style.cssText = (
      "color:#666;font-size:10px;margin:4px 0 0;" +
      "text-align:right;font-family:monospace;flex-shrink:0;"
    );

    inner.appendChild(hdr);
    inner.appendChild(fr);
    inner.appendChild(ftr);
    ov.appendChild(inner);
    document.body.appendChild(ov);

    overlay = ov;
    previewFrame = fr;
  }

  window.addEventListener("message", function (e) {
    if (!e.data) return;

    if (e.data.type === "4dpaper-open-camera") {
      if (!overlay) buildOverlay();
      document.getElementById("fourd-cam-figid").textContent = "fig id: " + e.data.fig_id;
      previewFrame.src = e.data.preview_src + "?t=" + Date.now();
      overlay.style.display = "flex";

    } else if (e.data.type === "4dpaper-camera") {
      // Camera sync from the preview iframe inside the overlay
      var figId = e.data.fig_id;
      var camera = e.data.camera;
      fetch("/camera/" + figId, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(camera),
      }).then(function (r) {
        if (previewFrame && previewFrame.contentWindow) {
          previewFrame.contentWindow.postMessage(
            { type: "4dpaper-camera-ack", fig_id: figId, status: r.ok ? "ok" : "error" },
            "*"
          );
        }
      }).catch(function () {
        if (previewFrame && previewFrame.contentWindow) {
          previewFrame.contentWindow.postMessage(
            { type: "4dpaper-camera-ack", fig_id: figId, status: "error" },
            "*"
          );
        }
      });
    }
  });
})();

