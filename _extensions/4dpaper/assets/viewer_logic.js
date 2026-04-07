(function(){
  // ── Data Contract Initialization ──────────────────────────────────────────
  const config = window.FOURD_CONFIG;
  if (!config) {
    console.error("[4dpaper] Data Contract (FOURD_CONFIG) not found. UI initialization aborted.");
    return;
  }

  const FIG_ID = config.figureId;
  const FIG_ID_SAFE = FIG_ID.replace(/-/g, '_');
  const ACTIVE_FIELD = config.activeField;
  
  const _cache = new Map();
  async function _loadData(val) {
    if (!val) return null;
    if (_cache.has(val)) return _cache.get(val);
    
    let arr;
    if (val.endsWith('.bin')) {
      const resp = await fetch(val);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const buf = await resp.arrayBuffer();
      arr = new Float32Array(buf);
    } else {
      // Decode Base64 (legacy fallback)
      const bin = atob(val);
      const by = new Uint8Array(bin.length);
      for(let i=0; i<bin.length; i++) by[i] = bin.charCodeAt(i);
      arr = new Float32Array(by.buffer);
    }
    
    _cache.set(val, arr);
    return arr;
  }
  
  let _iact = null;
  let _locked = false;
  let _cont = null;
  let _renderer = null;
  let _isHovered = false;
  let _camTimer = null;

  // ── UI Control Toggles ────────────────────────────────────────────────────
  const _CS_ALL = ["axes", "field", "time"];
  window["csToggle_" + FIG_ID_SAFE] = function(name) {
    if (_locked) {
      _showLockedBadge();
      return;
    }
    _CS_ALL.forEach(mode => {
      const el = document.getElementById(`cs-pop-${mode}`);
      if (!el) return;
      el.style.display = (mode === name && el.style.display === "none") ? "flex" : "none";
    });
  };

  // ── Locking Mechanism ─────────────────────────────────────────────────────
  let _lockBadgeTimer = null;
  function _showLockedBadge() {
    const b = document.getElementById("cs-lock-badge");
    if (!b) return;
    b.style.display = "block";
    clearTimeout(_lockBadgeTimer);
    _lockBadgeTimer = setTimeout(() => { b.style.display = "none"; }, 1500);
  }

  function _setLocked(v) {
    _locked = v;
    const w = document.getElementById("cs-lock-widget");
    if (w) w.textContent = v ? "🔒" : "🔓";
    
    const s = document.getElementById("cs-lock-shield");
    if (s) s.style.display = v ? "block" : "none";
    
    const rw = window.renderWindow;
    const i = _iact || (rw && rw.getInteractor ? rw.getInteractor() : null);
    if (i && i.setEnabled) i.setEnabled(v ? 0 : 1);
    
    const c = _cont || (i && i.getContainer ? i.getContainer() : null);
    if (c && c.style) {
      c.style.pointerEvents = v ? "none" : "";
      c.style.touchAction = v ? "none" : "";
    }
    if (v && i && i.stopAnimating) i.stopAnimating();
  }

  // Initial Lock Sync
  if (config.showLockBtn) {
    if (window.parent !== window) {
      parent.postMessage({ type: "4dpaper-lock-query", fig_id: FIG_ID }, "*");
    } else {
      fetch("/camera-lock/" + FIG_ID)
        .then(r => r.json())
        .then(d => _setLocked(!!d.locked))
        .catch(() => {});
    }

    const _lw = document.getElementById("cs-lock-widget");
    if (_lw) {
      _lw.addEventListener("click", () => {
        const nv = !_locked;
        _setLocked(nv);
        if (window.parent !== window) {
          parent.postMessage({ type: "4dpaper-lock-toggle", fig_id: FIG_ID, locked: nv }, "*");
        } else {
          fetch("/camera-lock/" + FIG_ID, {
            method: "POST", 
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ locked: nv })
          }).catch(() => { _setLocked(!nv); });
        }
      });
    }
  }

  // ── Camera Synchronization ────────────────────────────────────────────────
  function _sendCam(renderer) {
    if (_locked) return;
    clearTimeout(_camTimer);
    _camTimer = setTimeout(() => {
      const cam = renderer.getActiveCamera();
      const camData = {
        position: cam.getPosition(),
        focal_point: cam.getFocalPoint(),
        view_up: cam.getViewUp(),
        parallel_scale: cam.getParallelScale(),
        parallel_projection: cam.getParallelProjection() ? 1 : 0
      };
      if (window.parent !== window) {
        parent.postMessage({ type: "4dpaper-camera", fig_id: FIG_ID, camera: camData }, "*");
      } else {
        fetch("/camera/" + FIG_ID, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(camData)
        }).catch(() => {});
      }
    }, 300);
  }

  window.addEventListener("message", (e) => {
    if (!e.data) return;
    
    // Camera Acknowledgement
    if (e.data.type === "4dpaper-camera-ack") {
      if (e.data.fig_id !== FIG_ID && e.data.fig_id !== "*") return;
    }

    // Locking State Updates
    if (config.showLockBtn) {
      if (e.data.type === "4dpaper-lock-state" && e.data.fig_id === FIG_ID) _setLocked(!!e.data.locked);
      if (e.data.type === "4dpaper-lock-ack" && e.data.fig_id === FIG_ID) {
        if (e.data.status !== "ok") _setLocked(!_locked);
      }
    }

    // Global Lock Broadcast
      if (e.data.type === "4dpaper-lock-all") {
      _locked = !!e.data.locked;
      const _rw = window.renderWindow;
      const _li = _rw && _rw.getInteractor ? _rw.getInteractor() : null;
      if (_li && _li.setEnabled) _li.setEnabled(_locked ? 0 : 1);
      const _lc = _cont || (_li && _li.getContainer ? _li.getContainer() : null);
      if (_lc && _lc.style) { _lc.style.pointerEvents = _locked ? "none" : ""; _lc.style.touchAction = _locked ? "none" : ""; }
      if (_locked && _li && _li.stopAnimating) _li.stopAnimating();
      const _lw = document.getElementById("cs-lock-widget");
      if (_lw) _lw.textContent = _locked ? "🔒" : "🔓";
      const _ls = document.getElementById("cs-lock-shield");
      if (_ls) _ls.style.display = _locked ? "block" : "none";
    }

    // Visibility
    if (e.data.type === "4dpaper-hide-lock-btn") {
      const _lhw = document.getElementById("cs-lock-widget");
      if (_lhw) _lhw.style.display = "none";
    }

    // Camera Application (Sync)
    if (_renderer && !_locked && e.data.type === "4dpaper-camera-apply") {
      const cam = e.data.camera;
      if (!cam) return;
      const c = _renderer.getActiveCamera();
      if (cam.position) c.setPosition(cam.position[0], cam.position[1], cam.position[2]);
      if (cam.focal_point) c.setFocalPoint(cam.focal_point[0], cam.focal_point[1], cam.focal_point[2]);
      if (cam.view_up) c.setViewUp(cam.view_up[0], cam.view_up[1], cam.view_up[2]);
      if (cam.parallel_scale != null) c.setParallelScale(cam.parallel_scale);
      if (cam.parallel_projection != null) c.setParallelProjection(!!cam.parallel_projection);
      window.renderWindow.render();
    }
  });

  // ── Orientation & Axes ────────────────────────────────────────────────────
  function _n3(v) { 
    const l = Math.sqrt(v[0]*v[0] + v[1]*v[1] + v[2]*v[2]); 
    return l < 1e-10 ? [0, 0, 1] : [v[0]/l, v[1]/l, v[2]/l]; 
  }
  function _cr(a, b) { return [a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2], a[0]*b[1] - a[1]*b[0]]; }
  function _dt(a, b) { return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]; }
  function _rot(v, axis, deg) {
    const a = _n3(axis), x = v[0], y = v[1], z = v[2];
    const c = Math.cos(deg * Math.PI / 180), s = Math.sin(deg * Math.PI / 180);
    const d = a[0]*x + a[1]*y + a[2]*z;
    return [
      x*c + (a[1]*z - a[2]*y)*s + a[0]*d*(1-c), 
      y*c + (a[2]*x - a[0]*z)*s + a[1]*d*(1-c), 
      z*c + (a[0]*y - a[1]*x)*s + a[2]*d*(1-c)
    ];
  }

  let _svg = null;
  function _drawAxes() {
    if (!_renderer || !_svg) return;
    const cam = _renderer.getActiveCamera();
    const pos = cam.getPosition(), fp = cam.getFocalPoint(), vup = cam.getViewUp();
    const vd = _n3([fp[0]-pos[0], fp[1]-pos[1], fp[2]-pos[2]]);
    const right = _n3(_cr(vd, vup));
    const up = _cr(right, vd);
    const cx = 28, cy = 28, R = 22;
    const proj = (v) => [cx + R*_dt(v, right), cy - R*_dt(v, up)];
    
    const axes = [
      { w: [1, 0, 0], col: "#ff6666", lcol: "#ff9999", lbl: "X", hpd: 'data-dir="1,0,0"' },
      { w: [0, 1, 0], col: "#66cc66", lcol: "#99cc99", lbl: "Y", hpd: 'data-dir="0,1,0"' },
      { w: [0, 0, 1], col: "#6699ff", lcol: "#99aaff", lbl: "Z", hpd: 'data-dir="0,0,1"' }
    ];
    
    let html = "";
    axes.forEach(ax => {
      const tip = proj(ax.w);
      const tx = tip[0].toFixed(1), ty = tip[1].toFixed(1);
      const dx = tip[0] - cx, dy = tip[1] - cy, len = Math.sqrt(dx*dx + dy*dy) || 1;
      const nx = -dy/len * 3.5, ny = dx/len * 3.5;
      const bx1 = (tip[0] - dx/len*7 + nx).toFixed(1), by1 = (tip[1] - dy/len*7 + ny).toFixed(1);
      const bx2 = (tip[0] - dx/len*7 - nx).toFixed(1), by2 = (tip[1] - dy/len*7 - ny).toFixed(1);
      
      html += `<line x1="${cx}" y1="${cy}" x2="${tx}" y2="${ty}" ${ax.hpd} stroke="${ax.col}" stroke-width="2.5"/>`;
      html += `<polygon points="${tx},${ty} ${bx1},${by1} ${bx2},${by2}" ${ax.hpd} fill="${ax.col}"/>`;
      html += `<text x="${(tip[0] + dx/len*5).toFixed(1)}" y="${(tip[1] + dy/len*5+3).toFixed(1)}" ${ax.hpd} font-size="9" fill="${ax.lcol}" font-family="monospace">${ax.lbl}</text>`;
    });
    _svg.innerHTML = html;
  }
  function _axLoop() { _drawAxes(); requestAnimationFrame(_axLoop); }

  window["csSetView_" + FIG_ID_SAFE] = function(dir, vup) {
    if (!_renderer) return;
    const cam = _renderer.getActiveCamera();
    const fp = cam.getFocalPoint(), dist = cam.getDistance();
    const pn = _n3(dir);
    const up = vup ? _n3(vup) : ((Math.abs(pn[2]) > 0.9) ? [0, 1, 0] : [0, 0, 1]);
    cam.setPosition(fp[0] + pn[0]*dist, fp[1] + pn[1]*dist, fp[2] + pn[2]*dist);
    cam.setViewUp(up[0], up[1], up[2]);
    cam.setFocalPoint(fp[0], fp[1], fp[2]);
    _renderer.resetCameraClippingRange();
    if (_iact) _iact.setEnabled(1);
    if (window.renderWindow) window.renderWindow.render();
    _sendCam(_renderer);
  };

  window["csRotate_" + FIG_ID_SAFE] = function(dx, dy) {
    if (!_renderer) return;
    const cam = _renderer.getActiveCamera();
    const pos = cam.getPosition(), fp = cam.getFocalPoint(), vup = cam.getViewUp();
    const rel = [pos[0]-fp[0], pos[1]-fp[1], pos[2]-fp[2]];
    const right = _n3(_cr(rel, vup));
    const pitch = _rot(rel, right, dy);
    const yawAxis = _n3(vup);
    const yaw = _rot(pitch, yawAxis, dx);
    cam.setPosition(fp[0] + yaw[0], fp[1] + yaw[1], fp[2] + yaw[2]);
    cam.setViewUp(vup[0], vup[1], vup[2]);
    _renderer.resetCameraClippingRange();
    if (window.renderWindow) window.renderWindow.render();
    _sendCam(_renderer);
  };

  // ── Field Switching Logic ─────────────────────────────────────────────────
  function _initFields() {
    if (!config.availableFields || config.availableFields.length <= 1) return;
    const fieldData = config.fieldData;
    const fieldRanges = config.fieldRanges;
    const origField = config.activeField;
    const fSel = document.getElementById("cs-field-sel");
    const fBadge = document.getElementById("cs-field-badge");

    // Populate dropdown
    if (fSel) {
      fSel.innerHTML = "";
      // Add original field first
      const optOrig = document.createElement("option");
      optOrig.value = origField;
      optOrig.textContent = origField;
      optOrig.selected = true;
      fSel.appendChild(optOrig);

      // Add others
      Object.keys(fieldData).forEach(f => {
        if (f === origField) return;
        const opt = document.createElement("option");
        opt.value = f;
        opt.textContent = f;
        fSel.appendChild(opt);
      });
    }
    
    
    // Binary data is handled by the global _loadData helper

    (function _wM(){
      if(!_renderer) { setTimeout(_wM, 200); return; }
      const acts = _renderer.getActors();
      for(let i=0; i<acts.length; i++) {
        const mp = acts[i].getMapper(); if(!mp || !mp.getInputData) continue;
        const pd = mp.getInputData();
        if(pd && pd.getPointData && pd.getPointData().getArrayByName(origField)) {
          if(fSel) fSel.addEventListener("change", async () => {
            const f = fSel.value;
            if(!fieldData[f] && f !== origField) return;
            try {
              if(fBadge) { fBadge.innerHTML = "&#8230;"; fBadge.style.background = "#555"; fBadge.style.display = "inline-block"; }
              const arr = pd.getPointData().getArrayByName(origField);
              
              const data = await _loadData(fieldData[f]);
              if(data) arr.setData(data, 1);
              
              arr.modified(); pd.modified();
              const rng = fieldRanges[f];
              if(rng) mp.setScalarRange(rng[0], rng[1]);
              try { 
                const a2 = _renderer.getActors2D ? _renderer.getActors2D() : []; 
                for(let k=0; k<a2.length; k++) if(a2[k].setTitle) a2[k].setTitle(f); 
              } catch(e2) {}
              window.renderWindow.render();
              if(fBadge) { 
                fBadge.innerHTML = "&#10003; " + f; 
                fBadge.style.background = "rgba(0,140,0,0.85)"; 
                setTimeout(() => { fBadge.style.display = "none"; }, 2000); 
              }
              try { parent.postMessage({type: "4dpaper-field-update", fig_id: FIG_ID, data: {field: f}}, "*"); } catch(e3) {}
            } catch(err) {
              if(fBadge) { fBadge.innerHTML = "&#10007; error"; fBadge.style.background = "rgba(180,0,0,0.85)"; fBadge.style.display = "inline-block"; }
              console.error("[4dpaper] field switch error:", err);
            }
          });
          return;
        }
      }
      setTimeout(_wM, 200);
    })();
  }

  // ── Time Stepping Logic ───────────────────────────────────────────────────
  function _initTime() {
    if (!config.timeLabels || config.timeLabels.length <= 1) return;
    const tSlider = document.getElementById("cs-time-slider");
    const tVal = document.getElementById("cs-time-val");
    const tIdx = document.getElementById("cs-time-idx");
    const tMax = document.getElementById("cs-time-max");
    
    if (tSlider) tSlider.max = config.timeData.length - 1;
    if (tMax) tMax.textContent = config.timeData.length - 1;
    if (tVal && config.timeLabels[0]) tVal.textContent = config.timeLabels[0];

    let tTimer = null;
    let _activeUpdate = 0;

    // Binary data is handled by the global _loadData helper

    (function _wT(){
      if(!_renderer) { setTimeout(_wT, 200); return; }
      const acts = _renderer.getActors();
      for(let i=0; i<acts.length; i++) {
        const mp = acts[i].getMapper(); if(!mp || !mp.getInputData) continue;
        const pd = mp.getInputData();
        if(pd && pd.getPointData && pd.getPointData().getArrayByName(config.activeField)) {
          if(tSlider) tSlider.addEventListener("input", async () => {
            const idx = parseInt(tSlider.value);
            if(tVal && config.timeLabels[idx] !== undefined) tVal.textContent = config.timeLabels[idx];
            if(tIdx) tIdx.textContent = idx;
            
            const myUpdate = ++_activeUpdate;
            const dataUrl = config.timeData[idx]; 
            if(!dataUrl && idx !== config.timeIdx) return;
            
            try {
              const data = await _loadData(dataUrl);
              if (myUpdate !== _activeUpdate) return; // Prevent race conditions
              
              const a = pd.getPointData().getArrayByName(config.activeField);
              if (data) a.setData(data, 1);
              a.modified(); pd.modified();
              mp.setScalarRange(config.timeGlobalRange[0], config.timeGlobalRange[1]);
              window.renderWindow.render();
            } catch(e1) { console.error("[4dp] t-step:", e1); }
            
            clearTimeout(tTimer);
            tTimer = setTimeout(() => {
              try { parent.postMessage({type: "4dpaper-field-update", fig_id: FIG_ID, data: {time: String(idx)}}, "*"); } catch(e2) {}
            }, 100);
          });
          return;
        }
      }
      setTimeout(_wT, 200);
    })();
  }

  // ── Main Initialization Loop ──────────────────────────────────────────────
  (function _wR(){
    const rw = window.renderWindow;
    if(rw && rw.getRenderers) {
      const rs = rw.getRenderers();
      for(let i=0; i<rs.length; i++) {
        const r = rs[i];
        if(r && r.getActors && r.getActors().length > 0) {
          _renderer = r;
          _cont = window.renderWindow.getInteractor().getContainer();
          if(_cont) {
            _cont.addEventListener("mouseenter", () => { _isHovered = true; window.focus(); });
            _cont.addEventListener("mouseleave", () => { _isHovered = false; });
            _cont.addEventListener("wheel", (e) => { e.preventDefault(); }, { passive: false });
          }
          
          _setLocked(_locked);
          _svg = document.getElementById("cs-svg-axes");
          if(_svg && config.showOrientation) {
            _svg.addEventListener("click", (e) => {
              const dv = e.target.getAttribute("data-dir"); if(!dv) return;
              if(_locked) { _showLockedBadge(); return; }
              window["csSetView_" + FIG_ID_SAFE](dv.split(",").map(Number));
            });
            _axLoop();
          }
          
          _iact = window.renderWindow.getInteractor();
          if(_iact) _iact.setEnabled(_locked ? 0 : 1);
          
          document.addEventListener("pointerup", () => _sendCam(_renderer));
          document.addEventListener("mouseup", () => _sendCam(_renderer));
          document.addEventListener("touchend", () => _sendCam(_renderer));
          
          _initFields();
          _initTime();
          return;
        }
      }
    }
    setTimeout(_wR, 200);
  })();

  // Global Keyboard Shortcuts
  window.addEventListener("keydown", (e) => {
    if(!_renderer || !_isHovered) return;
    const k = e.key.toLowerCase();
    if(k === "x") { window["csSetView_" + FIG_ID_SAFE]([1,0,0], [0,0,1]); }
    else if(k === "y") { window["csSetView_" + FIG_ID_SAFE]([0,1,0], [0,0,1]); }
    else if(k === "z") { window["csSetView_" + FIG_ID_SAFE]([0,0,1], [0,1,0]); }
    else if(k === "i") { window["csSetView_" + FIG_ID_SAFE]([1,1,1], [0,0,1]); }
    else if(e.key === "ArrowUp")    { window["csRotate_" + FIG_ID_SAFE](0, -90); }
    else if(e.key === "ArrowDown")  { window["csRotate_" + FIG_ID_SAFE](0, 90); }
    else if(e.key === "ArrowLeft")  { window["csRotate_" + FIG_ID_SAFE](-90, 0); }
    else if(e.key === "ArrowRight") { window["csRotate_" + FIG_ID_SAFE](90, 0); }
    if(e.key.startsWith("Arrow")) { e.preventDefault(); }
  });

})();
