(function(){
  const config = window.FOURD_PANEL_CONFIG || { id: "unknown", sync: false };
  const PANEL_ID = config.id;
  const SYNC_MODE = config.sync;

  window.addEventListener("message", function(e) {
    if (!e.data) return;

    // Camera Synchronization
    if (SYNC_MODE && e.data.type === "4dpaper-camera") {
      const msg = Object.assign({}, e.data, { fig_id: PANEL_ID });
      top.postMessage(msg, "*");
      const iframes = document.querySelectorAll("iframe");
      for (let i = 0; i < iframes.length; i++) {
        iframes[i].contentWindow.postMessage({ type: "4dpaper-camera-apply", camera: e.data.camera }, "*");
      }
    } else if (!SYNC_MODE && (e.data.type === "4dpaper-camera" || e.data.type === "4dpaper-field-update")) {
      top.postMessage(e.data, "*");
    }

    // Acknowledgements
    if (e.data.type === "4dpaper-camera-ack" || e.data.type === "4dpaper-field-ack") {
      const iframes2 = document.querySelectorAll("iframe");
      const ackMsg = SYNC_MODE ? Object.assign({}, e.data, { fig_id: "*" }) : e.data;
      for (let j = 0; j < iframes2.length; j++) {
        iframes2[j].contentWindow.postMessage(ackMsg, "*");
      }
    }

    // Field Updates
    if (e.data.type === "4dpaper-field-update" && SYNC_MODE) {
      top.postMessage(e.data, "*");
    }

    // Locking Queries
    if (e.data.type === "4dpaper-lock-query" || e.data.type === "4dpaper-lock-toggle") {
      top.postMessage(e.data, "*");
    }

    // Locking State Apply
    if (e.data.type === "4dpaper-lock-state" || e.data.type === "4dpaper-lock-ack") {
      const iframes3 = document.querySelectorAll("iframe");
      for (let k = 0; k < iframes3.length; k++) {
        iframes3[k].contentWindow.postMessage(e.data, "*");
      }
    }
  });
})();
