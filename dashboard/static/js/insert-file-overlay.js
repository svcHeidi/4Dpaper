/**
 * Insert File — vanilla DOM overlay (same pattern as insert-figure-overlay.js).
 * Drag-drop files/folders → upload to staging → symlink to data/ → generate include shortcode
 */
(function () {
  function getCodeEditor() {
    // Works with CodeMirror (used in new dashboard)
    return typeof state !== 'undefined' && state.codeEditor ? state.codeEditor : null;
  }

  function insertShortcode(shortcode) {
    var ed = getCodeEditor();
    if (!ed) throw new Error("Editor not found (cannot insert)");
    var v = ed.getValue() || "";
    if (v && !v.endsWith("\n")) v += "\n";
    ed.setValue(v + shortcode + "\n", -1);
    ed.clearSelection();
    ed.focus();
  }

  async function uploadFiles(files) {
    if (!files || !files.length) throw new Error("No files selected");

    var uploadId = "file_" + Date.now();
    var total = files.length;
    var done = 0;
    var statusEl = document.getElementById("insert-file-drop-status");

    function setStatus(msg) {
      if (statusEl) statusEl.textContent = msg;
    }

    setStatus("Uploading " + total + " file(s)...");

    for (var i = 0; i < files.length; i++) {
      var f = files[i];
      var rel = f.webkitRelativePath || f.name;
      var resp = await fetch("/upload/file", { 
        method: "POST",
        headers: {
          "X-Upload-Id": uploadId,
          "X-Rel-Path": encodeURIComponent(rel)
        },
        body: f 
      });
      if (!resp.ok) {
        throw new Error("Upload failed at " + (i + 1) + "/" + total + " (" + resp.status + ")");
      }
      done++;
      setStatus("Uploading " + done + "/" + total + "...");
    }

    setStatus("Staging + generating shortcode...");
    var fin = await fetch("/upload/finish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        upload_id: uploadId,
        mode: "file"  // Different processing mode
      }),
    });

    if (!fin.ok) throw new Error("Finish failed: " + fin.status);
    var data = await fin.json();
    if (!data || data.status !== "ok") {
      throw new Error((data && data.detail) ? data.detail : "Finish failed");
    }

    insertShortcode(data.shortcode);
    setStatus("Inserted ✓");
    return data;
  }

  function wireDropzone(ov) {
    var dz = ov.querySelector("#insert-file-dropzone");
    var inp = ov.querySelector("#insert-file-input");
    var btn = ov.querySelector("#insert-file-btn");
    if (!dz || !inp) return;

    if (btn) {
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        inp.value = "";
        inp.click();
      });
    }

    inp.addEventListener("change", function () {
      var files = Array.from(inp.files || []);
      if (!files.length) return;
      uploadFiles(files).catch(function (err) {
        var statusEl = document.getElementById("insert-file-drop-status");
        if (statusEl) statusEl.textContent = "Error: " + (err.message || String(err));
      });
      inp.value = "";
    });

    dz.addEventListener("dragover", function (e) {
      e.preventDefault();
      dz.style.background = "rgba(37,99,235,0.15)";
    });
    dz.addEventListener("dragleave", function () {
      dz.style.background = "rgba(2,6,23,0.45)";
    });
    dz.addEventListener("drop", function (e) {
      e.preventDefault();
      dz.style.background = "rgba(2,6,23,0.45)";
      var files = Array.from(e.dataTransfer && e.dataTransfer.files ? e.dataTransfer.files : []);
      uploadFiles(files).catch(function (err) {
        var statusEl = document.getElementById("insert-file-drop-status");
        if (statusEl) statusEl.textContent = "Error: " + (err.message || String(err));
      });
    });
  }

  function buildOnce() {
    if (document.getElementById("insert-file-overlay")) return;

    var ov = document.createElement("div");
    ov.id = "insert-file-overlay";
    ov.style.cssText = [
      "display:none",
      "position:fixed",
      "inset:0",
      "z-index:2000000",
      "background:rgba(0,0,0,0.55)",
      "align-items:center",
      "justify-content:center",
      "padding:16px",
      "box-sizing:border-box",
    ].join(";");

    ov.innerHTML =
      '<div id="insert-file-modal-backdrop-hit" style="position:absolute;inset:0;z-index:0;cursor:default;"></div>' +
      '<div style="position:relative;z-index:1;width:min(400px,92vw);background:#0f172a;border:1px solid #263244;' +
      'border-radius:8px;padding:10px 12px;box-shadow:0 16px 48px rgba(0,0,0,0.55);pointer-events:auto;">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">' +
      '<span style="color:#ddd;font-size:13px;font-weight:700;">Insert File</span>' +
      '<button type="button" id="insert-file-close-x" title="Close" ' +
      'style="font-size:11px;padding:4px 10px;border-radius:4px;border:1px solid #475569;background:#1e293b;color:#e2e8f0;cursor:pointer;">' +
      "Close</button></div>" +
      '<div id="insert-file-dropzone" style="border:1px dashed #3b82f6;border-radius:8px;padding:10px 12px;margin:0;' +
      'background:rgba(2,6,23,0.45);cursor:default;">' +
      '<input type="file" id="insert-file-input" multiple ' +
      'style="position:absolute;width:0;height:0;opacity:0;pointer-events:none;" tabindex="-1" aria-hidden="true"/>' +
      '<div style="color:#e2e8f0;font-size:12px;line-height:1.4;">' +
      'Drop files here, or ' +
      '<button type="button" id="insert-file-btn" ' +
      'style="background:none;border:none;color:#93c5fd;text-decoration:underline;cursor:pointer;padding:0;font:inherit;">' +
      "choose files…</button> " +
      '<span style="color:#64748b;font-size:11px;">(.bib, .tex, .csv, etc.)</span></div>' +
      '<div id="insert-file-drop-status" style="margin-top:6px;color:#8ab4ff;font-size:10px;font-family:monospace;min-height:14px;"></div>' +
      "</div></div>";

    document.body.appendChild(ov);

    wireDropzone(ov);

    function hide() {
      ov.style.display = "none";
    }

    ov.querySelector("#insert-file-modal-backdrop-hit").addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      hide();
    });
    ov.querySelector("#insert-file-close-x").addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      hide();
    });

    document.addEventListener(
      "keydown",
      function onEsc(ev) {
        if (ev.key !== "Escape") return;
        var o = document.getElementById("insert-file-overlay");
        if (!o || getComputedStyle(o).display === "none") return;
        hide();
      },
      true
    );
  }

  window.showInsertFileModal = function () {
    buildOnce();
    var ov = document.getElementById("insert-file-overlay");
    if (ov) ov.style.display = "flex";
  };

  window.hideInsertFileModal = function () {
    var ov = document.getElementById("insert-file-overlay");
    if (ov) ov.style.display = "none";
  };
})();
