(function(){
  if (window.__tabAlignProbeDone) return;
  window.__tabAlignProbeDone = true;

  function deepQueryAll(selector){
    var out=[];
    function walk(root){
      if(!root) return;
      try{ root.querySelectorAll(selector).forEach(function(el){ out.push(el); }); }catch(e){}
      var nodes=[];
      try{ nodes = root.querySelectorAll('*'); }catch(e2){ return; }
      for(var i=0;i<nodes.length;i++){ if(nodes[i].shadowRoot) walk(nodes[i].shadowRoot); }
    }
    walk(document.documentElement);
    return out;
  }

  // #region agent log
  function send(payload){
    fetch('http://127.0.0.1:7740/ingest/40e615c9-5ddc-404d-9a79-8f3c1bd53150',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'53f858'},body:JSON.stringify(payload)}).catch(function(){});
  }
  // #endregion

  function probe(){
    var wraps = deepQueryAll('.editor-tabwrap');
    var data = {wrapCount: wraps.length, samples: []};
    for(var i=0;i<Math.min(4, wraps.length); i++){
      var w = wraps[i];
      var labelHost = null;
      var closeHost = null;
      var all = [];
      try { all = w.querySelectorAll('*'); } catch (e0) {}
      for (var j = 0; j < all.length; j++) {
        var n = all[j];
        var cls = String(n.className || '');
        if (!labelHost && cls.indexOf('editor-tab-label') >= 0) labelHost = n;
        if (!closeHost && cls.indexOf('editor-tab-close') >= 0) closeHost = n;
        if (n.shadowRoot) {
          try {
            n.shadowRoot.querySelectorAll('*').forEach(function(sn){
              var scls = String(sn.className || '');
              if (!labelHost && scls.indexOf('editor-tab-label') >= 0) labelHost = sn;
              if (!closeHost && scls.indexOf('editor-tab-close') >= 0) closeHost = sn;
            });
          } catch (e1) {}
        }
      }
      var s = {idx:i, className:String(w.className||'')};
      s.foundLabel = !!labelHost;
      s.foundClose = !!closeHost;
      if(labelHost){
        var lr = labelHost.getBoundingClientRect();
        s.labelTop = lr.top;
        s.labelCenter = (lr.top + lr.bottom)/2;
        var lb = (labelHost.shadowRoot && labelHost.shadowRoot.querySelector('.bk-btn')) || null;
        if(lb){
          var cs = getComputedStyle(lb);
          s.labelLineHeight = cs.lineHeight;
          s.labelAlignItems = cs.alignItems;
          s.labelFontSize = cs.fontSize;
        }
      }
      if(closeHost){
        var cr = closeHost.getBoundingClientRect();
        s.closeTop = cr.top;
        s.closeCenter = (cr.top + cr.bottom)/2;
        var cb = (closeHost.shadowRoot && closeHost.shadowRoot.querySelector('.bk-btn')) || null;
        var svg = (closeHost.shadowRoot && closeHost.shadowRoot.querySelector('svg')) || null;
        if(cb){
          var ccs = getComputedStyle(cb);
          s.closeLineHeight = ccs.lineHeight;
          s.closeAlignItems = ccs.alignItems;
        }
        if(svg){ s.svgTransform = getComputedStyle(svg).transform; }
      }
      if(s.labelCenter != null && s.closeCenter != null){
        s.centerDelta = +(s.labelCenter - s.closeCenter).toFixed(3);
      }
      var hosts = [];
      var nodes = [];
      try { nodes = w.querySelectorAll('*'); } catch (e4) {}
      for (var k = 0; k < nodes.length; k++) {
        var h = nodes[k];
        if (!h.shadowRoot) continue;
        var b = null;
        try { b = h.shadowRoot.querySelector('.bk-btn'); } catch (e5) {}
        if (!b) continue;
        var hr = h.getBoundingClientRect();
        var br = b.getBoundingClientRect();
        hosts.push({
          hostTag: h.tagName,
          hostClass: String(h.className || ''),
          hostW: +(hr.width.toFixed(2)),
          hostCenter: +(((hr.top + hr.bottom) / 2).toFixed(3)),
          btnCenter: +(((br.top + br.bottom) / 2).toFixed(3)),
          btnLineHeight: getComputedStyle(b).lineHeight,
          btnText: (b.textContent || '').trim().slice(0, 80),
        });
      }
      s.hostButtons = hosts;
      data.samples.push(s);
    }

    function nearestEditorTabwrap(node){
      var cur = node;
      while(cur){
        try{
          if (cur.classList && cur.classList.contains('editor-tabwrap')) return cur;
        }catch(e){}
        if (cur.parentNode){
          cur = cur.parentNode;
          continue;
        }
        if (cur.host){
          cur = cur.host;
          continue;
        }
        break;
      }
      return null;
    }

    var allBtns = [];
    function walkBtns(root){
      if(!root) return;
      try{
        root.querySelectorAll('.bk-btn').forEach(function(b){ allBtns.push(b); });
      }catch(e){}
      var nodes = [];
      try{ nodes = root.querySelectorAll('*'); }catch(e2){ return; }
      for(var i=0;i<nodes.length;i++){ if(nodes[i].shadowRoot) walkBtns(nodes[i].shadowRoot); }
    }
    walkBtns(document.documentElement);

    var grouped = {};
    for (var bi = 0; bi < allBtns.length; bi++){
      var b = allBtns[bi];
      var wrap = nearestEditorTabwrap(b);
      if(!wrap) continue;
      var key = String(wrap.className || 'wrap');
      if(!grouped[key]) grouped[key] = [];
      var br = b.getBoundingClientRect();
      var txt = (b.textContent || '').trim();
      var hasSvg = false;
      try { hasSvg = !!b.querySelector('svg'); } catch(e3){}
      grouped[key].push({
        text: txt.slice(0, 80),
        hasSvg: hasSvg,
        w: +(br.width.toFixed(2)),
        h: +(br.height.toFixed(2)),
        center: +(((br.top+br.bottom)/2).toFixed(3)),
        lineHeight: getComputedStyle(b).lineHeight,
        textCenter: (function(){
          try {
            var tn = null;
            var kids = b.childNodes || [];
            for (var ti = 0; ti < kids.length; ti++) {
              var n = kids[ti];
              if (n && n.nodeType === 3 && String(n.textContent || '').trim()) { tn = n; break; }
            }
            if (!tn) return null;
            var r = document.createRange();
            r.selectNodeContents(tn);
            var tr = r.getBoundingClientRect();
            return +(((tr.top + tr.bottom)/2).toFixed(3));
          } catch (e4) { return null; }
        })(),
      });
    }
    data.composedButtonsByWrap = grouped;

    send({sessionId:'53f858',runId:'tab-align-run1',hypothesisId:'H1-H4',location:'tab_align_probe.js:probe',message:'tab alignment metrics',data:data,timestamp:Date.now()});
  }

  setTimeout(probe, 500);
  setTimeout(probe, 2000);
})();
