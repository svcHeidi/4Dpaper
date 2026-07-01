(function(){
  const config = window.FOURD_PANEL_CONFIG || { id: "unknown", sync: false };
  const PANEL_ID = config.id;
  const SYNC_MODE = config.sync;

  /* The panel page is loaded as a srcdoc iframe, so its origin is "null".
   * Messages it receives come from the parent relay page (same server origin)
   * or from the vtk.js figure iframes nested inside it (also srcdoc → "null").
   * Accept both. */
  const SELF_ORIGIN = window.location.origin; // "null" for srcdoc
  function isTrustedOrigin(e) {
    return e.origin === SELF_ORIGIN || e.origin === "null";
  }

  window.addEventListener("message", function(e) {
    if (!e.data) return;

    /* Drop messages from unknown origins. */
    if (!isTrustedOrigin(e)) return;

    // Camera Synchronization
    if (e.data.type === "4dpaper-camera") {
      const iframes = document.querySelectorAll("iframe");
      const isFirst = iframes.length > 0 && e.source === iframes[0].contentWindow;
      
      if (SYNC_MODE || isFirst) {
        const msg = Object.assign({}, e.data, { fig_id: PANEL_ID });
        top.postMessage(msg, "*"); // relay to parent
        for (let i = 0; i < iframes.length; i++) {
          if (iframes[i].contentWindow !== e.source) {
            iframes[i].contentWindow.postMessage({ type: "4dpaper-camera-apply", camera: e.data.camera }, "*"); // srcdoc iframes
          }
        }
      } else {
        top.postMessage(e.data, "*"); // relay up to parent
      }
    } else if (!SYNC_MODE && e.data.type === "4dpaper-field-update") {
      top.postMessage(e.data, "*"); // relay up to parent
    }

    // Acknowledgements
    if (e.data.type === "4dpaper-camera-ack" || e.data.type === "4dpaper-field-ack") {
      const iframes2 = document.querySelectorAll("iframe");
      const ackMsg = SYNC_MODE ? Object.assign({}, e.data, { fig_id: "*" }) : e.data;
      for (let j = 0; j < iframes2.length; j++) {
        iframes2[j].contentWindow.postMessage(ackMsg, "*"); // srcdoc iframes
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
        iframes3[k].contentWindow.postMessage(e.data, "*"); // srcdoc iframes
      }
    }
  });
})();
