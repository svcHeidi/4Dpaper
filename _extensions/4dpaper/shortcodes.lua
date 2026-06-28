--[[
4DPaper shortcode handler.

Usage in .qmd:
  {{< 4d-image src="case.foam" field="Vm" id="fig-vm" >}}
  {{< 4d-image src="case.foam" field="activationTime" id="fig-at" time="last" caption="Activation time" >}}

HTML output: embeds state/figures/<id>.html as raw HTML block (interactive vtk.js)
PDF output:  embeds state/figures/<id>.png as a standard Markdown image
--]]

local _relay_injected = false
-- App mode: set by dashboard when building preview HTML.
-- Figures are served as static files (/state/figures/<id>.html) instead of
-- being inlined as srcdoc — pandoc processes ~50KB instead of ~15MB, ~10x faster.
local _app_mode = os.getenv("FOURD_APP_MODE") == "1"
-- Paper-view mode: embed static PNG <img> instead of interactive iframes.
-- Set by dashboard when building the paperview profile.
local _paper_view = os.getenv("FOURD_PAPER_VIEW") == "1"

-- ── Shared relay script (injected once per page) ──────────────────────────
-- Handles two concerns:
--  1. Camera overlay: position:fixed inside THIS document (analysis_report.html).
--     The overlay covers the full paper-preview pane — no cross-frame DOM injection.
--  2. Figure message relay: handles camera/field messages from child iframes.
local _RELAY_SCRIPT = [=[
<script>
(function(){
  /* Debug bar removed — no on-page "[4d] …" message log, no console spam. */
  function _dbg(msg){}

  /* ── Camera overlay: lives in this document (paper preview) ──────── */
  if (!document.getElementById('fourd-cam-overlay')) {
    function _mk(t,c,h){var e=document.createElement(t);if(c)e.style.cssText=c;if(h)e.innerHTML=h;return e;}
    var _ov=_mk('div',
      'display:none;position:fixed;top:0;left:0;width:100%;height:100%;'+
      'z-index:2147483647;background:rgba(0,0,0,0.85);'+
      'align-items:center;justify-content:center;padding:24px;box-sizing:border-box;');
    _ov.id='fourd-cam-overlay';
    var _in=_mk('div',
      'width:100%;max-width:1200px;height:100%;display:flex;flex-direction:column;'+
      'background:#1a1a2e;border-radius:8px;padding:12px;'+
      'box-sizing:border-box;box-shadow:0 8px 32px rgba(0,0,0,0.6);');
    var _hd=_mk('div','display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;flex-shrink:0;');
    var _tx=_mk('span','color:#aaa;font-size:12px;font-family:monospace;',
      '\uD83D\uDCF7 Camera Setup \u2014 rotate the figure to your desired viewpoint');
    var _cb=_mk('button','background:none;border:none;color:#999;font-size:20px;cursor:pointer;padding:0 4px;flex-shrink:0;','\u2715');
    _cb.onclick=function(){_ov.style.display='none';};
    _hd.appendChild(_tx); _hd.appendChild(_cb);
    var _sb=_mk('div',
      'display:flex;justify-content:space-between;align-items:center;'+
      'margin-bottom:6px;flex-shrink:0;padding:6px 10px;background:#0d1117;border-radius:4px;');
    _sb.id='fourd-cam-stbar';
    var _st=_mk('span','color:#888;font-size:11px;font-family:monospace;',
      'Rotate then release \u2014 camera position saves automatically');
    _st.id='fourd-cam-sttxt';
    var _sr=_mk('span','color:#555;font-size:11px;font-family:monospace;',
      'After saving \u2192 click \u201cRebuild HTML\u201d to apply');
    _sb.appendChild(_st); _sb.appendChild(_sr);
    var _fr=_mk('iframe','flex:1;min-height:0;width:100%;border:none;border-radius:4px;display:block;');
    _fr.id='fourd-cam-iframe'; _fr.frameBorder='0';
    var _ft=_mk('p','color:#555;font-size:10px;margin:4px 0 0;text-align:right;font-family:monospace;flex-shrink:0;');
    _ft.id='fourd-cam-figid';
    _in.appendChild(_hd); _in.appendChild(_sb); _in.appendChild(_fr); _in.appendChild(_ft);
    _ov.appendChild(_in);
    document.body.appendChild(_ov);
    _dbg('overlay created in document');
  }

  /* ── Message handler: camera open, camera sync, field update ─────── */
  window.addEventListener("message",function(e){
    if(!e.data)return;
    _dbg('msg received: '+e.data.type);

    if(e.data.type==="4dpaper-open-camera"){
      _dbg('opening camera for '+e.data.fig_id);
      var _o=document.getElementById('fourd-cam-overlay');
      var _f=document.getElementById('fourd-cam-iframe');
      var _lb=document.getElementById('fourd-cam-figid');
      var _ss=document.getElementById('fourd-cam-sttxt');
      if(_lb)_lb.textContent='fig id: '+e.data.fig_id;
      if(_f)_f.src=e.data.preview_src+'?t='+Date.now();
      if(_ss){_ss.textContent='Rotate then release \u2014 camera position saves automatically';_ss.style.color='#888';}
      if(_o){_o.style.display='flex';_dbg('overlay shown for '+e.data.fig_id);}
      else{_dbg('ERROR: overlay element not found!');}

    } else if(e.data.type==="4dpaper-camera"){
      /* Check if message comes from a sync-panel subfigure (has data-panel attr) */
      var panelId=null;
      var allPanelFrames=document.querySelectorAll("iframe[data-panel]");
      for(var _pi=0;_pi<allPanelFrames.length;_pi++){
        if(allPanelFrames[_pi].contentWindow===e.source){
          panelId=allPanelFrames[_pi].getAttribute("data-panel");break;
        }
      }
      var camId=panelId||e.data.fig_id;
      var _f2=document.getElementById('fourd-cam-iframe');
      var _ss2=document.getElementById('fourd-cam-sttxt');
      fetch('/camera/'+camId,{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(e.data.camera)
      }).catch(function(){});

      if(panelId){
        var ack={type:'4dpaper-camera-ack',fig_id:'*',status:'ok'};
        var pFrames=document.querySelectorAll('iframe[data-panel="'+panelId+'"]');
        for(var _pj=0;_pj<pFrames.length;_pj++){
          if(pFrames[_pj].contentWindow !== e.source) {
            pFrames[_pj].contentWindow.postMessage({type:'4dpaper-camera-apply',camera:e.data.camera},'*');
          }
          pFrames[_pj].contentWindow.postMessage(ack,'*');
        }
      } else {
        var ack2={type:'4dpaper-camera-ack',fig_id:camId,status:'ok'};
        if(_f2&&_f2.contentWindow)_f2.contentWindow.postMessage(ack2,'*');
        if(e.source&&e.source!==(_f2&&_f2.contentWindow))e.source.postMessage(ack2,'*');
      }

    } else if(e.data.type==="4dpaper-field-update"){
      var figId2=e.data.fig_id;
      fetch('/field/'+figId2,{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(e.data.data)
      }).then(function(r){
        if(r.ok&&e.source)e.source.postMessage({type:'4dpaper-field-ack',fig_id:figId2,status:'ok'},'*');
      }).catch(function(){
        if(e.source)e.source.postMessage({type:'4dpaper-field-ack',fig_id:figId2,status:'error'},'*');
      });
    } else if(e.data.type==="4dpaper-lock-query"){
      var lockFigId=e.data.fig_id;
      fetch("/camera-lock/"+lockFigId)
        .then(function(r){return r.json();})
        .then(function(d){
          if(e.source)e.source.postMessage(
            {type:"4dpaper-lock-state",fig_id:lockFigId,locked:!!d.locked},"*");
        }).catch(function(){
          if(e.source)e.source.postMessage(
            {type:"4dpaper-lock-state",fig_id:lockFigId,locked:false},"*");
        });
    } else if(e.data.type==="4dpaper-lock-toggle"){
      var lockFigId2=e.data.fig_id;
      fetch("/camera-lock/"+lockFigId2,{
        method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({locked:!!e.data.locked})
      }).then(function(r){
        if(e.source)e.source.postMessage(
          {type:"4dpaper-lock-ack",fig_id:lockFigId2,status:r.ok?"ok":"error"},"*");
      }).catch(function(){
        if(e.source)e.source.postMessage(
          {type:"4dpaper-lock-ack",fig_id:lockFigId2,status:"error"},"*");
      });
    }
  });
})();
</script>
]=]

local function fourd_image(args, kwargs)
  local id      = pandoc.utils.stringify(kwargs["id"] or pandoc.Str(""))
  local caption = pandoc.utils.stringify(kwargs["caption"] or pandoc.Str(""))

  if id == "" then
    return pandoc.RawBlock("html",
      '<div style="color:red">⚠ 4d-image: missing required attribute <code>id</code></div>')
  end

  -- ── HTML output ───────────────────────────────────────────────────────────
  if quarto.doc.isFormat("html") then
    -- Paper-view: embed static PNG instead of interactive iframe
    if _paper_view then
      local png_path = "state/figures/" .. id .. ".png"
      local pf = io.open(png_path, "r")
      if pf then pf:close() end
      local cap_html = caption ~= "" and
        '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' ..
        caption .. '</figcaption>\n' or ""
      if not pf then
        return pandoc.RawBlock("html",
          '<figure class="fourd-figure" style="margin:1.5rem 0;">' ..
          '<div style="border:2px dashed #888;padding:1rem;text-align:center;">' ..
          '⚠ Figure <code>' .. id .. '</code> not rendered — click Rebuild HTML</div>' ..
          cap_html .. '</figure>')
      end
      return pandoc.RawBlock("html",
        '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
        '<img src="/state/figures/' .. id .. '.png" style="width:100%;display:block;">\n' ..
        cap_html .. '</figure>')
    end

    local fig_path = "state/figures/" .. id .. ".html"
    local exists = io.open(fig_path, "r")
    if exists then exists:close() end

    if not exists then
      return pandoc.RawBlock("html",
        '<div style="border:2px dashed #888;padding:1.5rem;text-align:center;' ..
        'border-radius:4px;margin:1rem 0">' ..
        '<strong>⚠ 4D Figure not yet rendered</strong><br>' ..
        'Figure ID: <code>' .. id .. '</code><br>' ..
        '<small>Click <strong>Rebuild HTML</strong> in the dashboard to generate.</small>' ..
        '</div>')
    end

    local relay_script = ""
    if not _relay_injected then
      _relay_injected = true
      relay_script = _RELAY_SCRIPT
    end

    local iframe
    if _app_mode then
      -- App mode: reference static file — pandoc doesn't inline the content.
      iframe = '<iframe src="/state/figures/' .. id .. '.html" width="100%" height="600px" ' ..
               'frameborder="0" style="border:none;border-radius:4px;display:block;"></iframe>'
    else
      -- Export mode: inline as srcdoc for a fully self-contained HTML file.
      local f = io.open(fig_path, "r")
      local content = f:read("*all")
      f:close()
      local escaped = content:gsub("&", "&amp;"):gsub('"', "&quot;")
      iframe = '<iframe srcdoc="' .. escaped .. '" width="100%" height="600px" ' ..
               'frameborder="0" style="border:none;border-radius:4px;display:block;"></iframe>'
    end

    return pandoc.RawBlock("html",
      '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
      iframe .. '\n' ..
      (caption ~= "" and
        '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' .. caption .. '</figcaption>\n'
        or "") ..
      '</figure>\n' ..
      relay_script)

    -- ── PDF / LaTeX output: embed vector .pdf if available, else .png ──────────
  else
    local pdf_path = "state/figures/" .. id .. ".pdf"
    local png_path = "state/figures/" .. id .. ".png"
    local pf = io.open(pdf_path, "r")
    local fig_path
    if pf then
      pf:close()
      fig_path = pdf_path
    else
      local f2 = io.open(png_path, "r")
      if f2 then f2:close(); fig_path = png_path end
    end
    if fig_path then
      local img = pandoc.Image(caption, fig_path, id, pandoc.Attr(id, {}, { width = "90%" }))
      return pandoc.Para({ img })
    else
      return pandoc.Para({
        pandoc.Str("[Figure "),
        pandoc.Code(id),
        pandoc.Str(" — run 'Export PDF' from the dashboard to generate this figure]"),
      })
    end
  end
end

local function fourd_video(args, kwargs)
  local id      = pandoc.utils.stringify(kwargs["id"]      or pandoc.Str(""))
  local caption = pandoc.utils.stringify(kwargs["caption"] or pandoc.Str(""))

  if id == "" then
    return pandoc.RawBlock("html",
      '<div style="color:red">⚠ 4d-video: missing required attribute <code>id</code></div>')
  end

  -- ── HTML output ───────────────────────────────────────────────────────────
  if quarto.doc.isFormat("html") then
    -- Paper-view: embed static video frame PNG instead of interactive video
    if _paper_view then
      local frame_path = "state/figures/" .. id .. "-frame.png"
      local pf = io.open(frame_path, "r")
      if pf then pf:close() end
      local cap_html = caption ~= "" and
        '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' ..
        caption .. '</figcaption>\n' or ""
      if not pf then
        return pandoc.RawBlock("html",
          '<figure class="fourd-figure" style="margin:1.5rem 0;">' ..
          '<div style="border:2px dashed #888;padding:1rem;text-align:center;">' ..
          '⚠ Video frame <code>' .. id .. '</code> not rendered — click Rebuild HTML</div>' ..
          cap_html .. '</figure>')
      end
      return pandoc.RawBlock("html",
        '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
        '<img src="/state/figures/' .. id .. '-frame.png" style="width:100%;display:block;">\n' ..
        cap_html .. '</figure>')
    end

    local html_path = "state/figures/" .. id .. "-video.html"
    local exists = io.open(html_path, "r")
    if exists then exists:close() end

    if not exists then
      return pandoc.RawBlock("html",
        '<div style="border:2px dashed #888;padding:1.5rem;text-align:center;' ..
        'border-radius:4px;margin:1rem 0">' ..
        '<strong>⚠ 4D Video not yet rendered</strong><br>' ..
        'Figure ID: <code>' .. id .. '</code><br>' ..
        '<small>Click <strong>Rebuild HTML</strong> in the dashboard to generate.</small>' ..
        '</div>')
    end

    local relay_script = ""
    if not _relay_injected then
      _relay_injected = true
      relay_script = _RELAY_SCRIPT
    end

    local cap_html = caption ~= "" and
      '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' .. caption .. '</figcaption>\n'
      or ""

    local body
    if _app_mode then
      local cam_onclick =
        "(function(){" ..
        "var o=document.getElementById('fourd-cam-overlay');" ..
        "var lb=document.getElementById('fourd-cam-figid');" ..
        "var f=document.getElementById('fourd-cam-iframe');" ..
        "var ss=document.getElementById('fourd-cam-sttxt');" ..
        "if(lb)lb.textContent='fig id: " .. id .. "';" ..
        "if(f)f.src='/state/figures/" .. id .. "-preview.html?t='+Date.now();" ..
        "if(ss){ss.textContent='Rotate - saves automatically';ss.style.color='#0a8';}" ..
        "if(o)o.style.display='flex';" ..
        "})()"
      -- Use JS to set iframe src with Date.now() so the browser never serves
      -- a cached version of the video HTML after a rebuild.
      local iframe_id = 'fourd-vid-' .. id
      body = '<div style="position:relative;display:inline-block;width:100%;">' ..
             '<iframe id="' .. iframe_id .. '" src="" width="100%" height="600px" ' ..
             'frameborder="0" style="border:none;border-radius:4px;display:block;"></iframe>' ..
             '<script>(function(){' ..
             'var f=document.getElementById("' .. iframe_id .. '");' ..
             'if(f)f.src="/state/figures/' .. id .. '-video.html?t="+Date.now();' ..
             '})();</script>' ..
             '<button onclick="' .. cam_onclick .. '" ' ..
             'style="position:absolute;top:8px;right:8px;z-index:10;' ..
             'background:rgba(0,0,0,0.65);color:#fff;border:none;border-radius:4px;' ..
             'padding:4px 10px;font-size:12px;cursor:pointer;">&#128247; Camera View</button>' ..
             '</div>'
    else
      local f = io.open(html_path, "r")
      body = f:read("*all")
      f:close()
    end

    return pandoc.RawBlock("html",
      '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
      body .. '\n' .. cap_html ..
      '</figure>\n' ..
      relay_script)

  -- ── PDF / LaTeX output: embed pre-rendered frame PNG ──────────────────────
  else
    local fig_path = "state/figures/" .. id .. "-frame.png"
    local f = io.open(fig_path, "r")
    if f then
      f:close()
      local img = pandoc.Image(caption, fig_path, id, pandoc.Attr(id, {}, { width = "90%" }))
      return pandoc.Para({ img })
    else
      return pandoc.Para({
        pandoc.Str("[Video "),
        pandoc.Code(id),
        pandoc.Str(" — run 'Export PDF' from the dashboard to generate this figure]"),
      })
    end
  end
end

local function fourd_panel(args, kwargs)
  local id      = pandoc.utils.stringify(kwargs["id"]      or pandoc.Str(""))
  local caption = pandoc.utils.stringify(kwargs["caption"] or pandoc.Str(""))
  local height  = pandoc.utils.stringify(kwargs["height"]  or pandoc.Str("800px"))
  local layout  = pandoc.utils.stringify(kwargs["layout"]  or pandoc.Str("1x1"))
  local camera_mode = pandoc.utils.stringify(kwargs["camera"]  or pandoc.Str("independent"))

  if id == "" then
    return pandoc.RawBlock("html",
      '<div style="color:red">⚠ 4d-panel: missing required attribute <code>id</code></div>')
  end

  -- ── HTML output: CSS grid of individual srcdoc iframes ────────────────────
  -- Each sub-figure is a direct srcdoc iframe (same depth as fourd_image).
  -- This avoids triple-nesting (page → composite srcdoc → data: iframe).
  if quarto.doc.isFormat("html") then
    -- Paper-view: embed composite PNG instead of interactive grid
    if _paper_view then
      local cap_html = caption ~= "" and
        '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' ..
        caption .. '</figcaption>\n' or ""

      -- Try to read the manifest for subfigure IDs (high-fidelity grid)
      local manifest_path = "state/figures/" .. id .. ".manifest.json"
      local mf = io.open(manifest_path, "r")
      local subfig_ids = {}
      local ncols = 1
      if mf then
        local ms = mf:read("*all"); mf:close()
        for s in ms:gmatch('"subfigures"%s*:%s*%[([^%]]*)%]') do
          for sub_id in s:gmatch('"([^"]+)"') do
            table.insert(subfig_ids, sub_id)
          end
        end
        local layout_str = ms:match('"layout"%s*:%s*"(%d+)x%d+"')
        ncols = tonumber(layout_str) or 1
      end

      if #subfig_ids > 0 then
        -- Build high-fidelity CSS grid of individual PNGs (PDF-like)
        local imgs = ""
        for _, sub_id in ipairs(subfig_ids) do
          imgs = imgs .. '<img src="/state/figures/' .. sub_id .. '.png" style="width:100%;display:block;">\n'
        end
        local grid_style = 'display:grid;grid-template-columns:repeat(' .. ncols .. ',1fr);gap:4px;width:100%;background:white;'
        return pandoc.RawBlock("html",
          '<figure class="fourd-figure" style="margin:1.5rem 0;background:white;padding:10px;border-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,0.05);">\n' ..
          '<div style="' .. grid_style .. '">' .. imgs .. '</div>\n' ..
          cap_html .. '</figure>')
      else
        -- Fallback: single composite PNG
        local png_path = "state/figures/" .. id .. ".png"
        local pf = io.open(png_path, "r")
        if pf then pf:close() end
        if not pf then
          return pandoc.RawBlock("html",
            '<figure class="fourd-figure" style="margin:1.5rem 0;">' ..
            '<div style="border:2px dashed #888;padding:1rem;text-align:center;">' ..
            '⚠ Panel <code>' .. id .. '</code> not rendered — click Rebuild HTML</div>' ..
            cap_html .. '</figure>')
        end
        return pandoc.RawBlock("html",
          '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
          '<img src="/state/figures/' .. id .. '.png" style="width:100%;display:block;">\n' ..
          cap_html .. '</figure>')
      end
    end

    -- Inject relay script once per page
    local relay_script = ""
    if not _relay_injected then
      _relay_injected = true
      relay_script = _RELAY_SCRIPT
    end

    if camera_mode == "sync" then
      -- Sync mode: embed each subfigure as a direct srcdoc iframe with data-panel attribute.
      -- This avoids data:text/html;base64 iframes which break vtk.js WebGL rendering.
      -- The top-level _RELAY_SCRIPT handles panel-sync camera broadcast.
      local ncols_s = layout:match("^(%d+)x") or "1"
      local nrows_s = layout:match("x(%d+)$") or "1"
      local ncols = tonumber(ncols_s) or 1
      local nrows = tonumber(nrows_s) or 1
      local sync_cells = {}
      local n = 1
      while true do
        local sub_id_val = kwargs["id" .. n]
        if not sub_id_val then break end
        local sub_id = pandoc.utils.stringify(sub_id_val)
        if sub_id == "" then break end
        local fig_path = "state/figures/" .. sub_id .. ".html"
        local cell_iframe
        if _app_mode then
          cell_iframe = '<iframe src="/state/figures/' .. sub_id .. '.html" ' ..
                        'data-panel="' .. id .. '" ' ..
                        'style="width:100%;height:100%;border:none;" frameborder="0"></iframe>'
        else
          local fh = io.open(fig_path, "r")
          if fh then
            local content = fh:read("*all"); fh:close()
            local escaped = content:gsub("&", "&amp;"):gsub('"', "&quot;")
            cell_iframe = '<iframe srcdoc="' .. escaped .. '" ' ..
                          'data-panel="' .. id .. '" ' ..
                          'style="width:100%;height:100%;border:none;" frameborder="0"></iframe>'
          else
            cell_iframe = '<div style="background:#222;display:flex;align-items:center;' ..
                          'justify-content:center;color:#888;font-family:sans-serif;font-size:0.85rem;">' ..
                          '⚠ ' .. sub_id .. ' not rendered</div>'
          end
        end
        table.insert(sync_cells, cell_iframe)
        n = n + 1
      end
      if #sync_cells == 0 then
        return pandoc.RawBlock("html",
          '<div style="border:2px dashed #888;padding:1.5rem;text-align:center;">' ..
          '⚠ 4D Panel <code>' .. id .. '</code> not yet rendered — ' ..
          'click <strong>Rebuild HTML</strong> in the dashboard.</div>')
      end
      local sync_grid = 'display:grid;grid-template-columns:repeat(' .. ncols .. ',1fr);' ..
                        'grid-template-rows:repeat(' .. nrows .. ',1fr);gap:4px;' ..
                        'width:100%;height:' .. height .. ';background:#111;'
      local lock_toolbar = '<div id="plb-' .. id .. '" style="' ..
        'display:flex;align-items:center;gap:8px;background:#181614;' ..
        'border-bottom:1px solid #3d3834;padding:3px 8px;' ..
        'font-family:system-ui,sans-serif;font-size:11px;">' ..
        '<button id="plb-btn-' .. id .. '" style="background:none;border:none;' ..
        'cursor:pointer;font-size:14px;padding:0;line-height:1;">&#x1F513;</button>' ..
        '<script>(function(){' ..
        'var PID="' .. id .. '";var _pl=false;' ..
        'function _bc(v){var f=document.querySelectorAll(' ..
        '"iframe[data-panel=\\""+PID+"\\"]");' ..
        'for(var i=0;i<f.length;i++)f[i].contentWindow.postMessage({type:"4dpaper-lock-all",locked:v},"*");}' ..
        'function _bh(){var f=document.querySelectorAll(' ..
        '"iframe[data-panel=\\""+PID+"\\"]");' ..
        'for(var i=0;i<f.length;i++)f[i].contentWindow.postMessage({type:"4dpaper-hide-lock-btn"},"*");}' ..
        'function _spl(v){_pl=v;' ..
        'var b=document.getElementById("plb-btn-"+PID);' ..
        'if(b)b.innerHTML=v?"&#x1F512;":"&#x1F513;";' ..
        '_bc(v);}' ..
        'fetch("/camera-lock/"+PID)' ..
        '.then(function(r){return r.json();})' ..
        '.then(function(d){_spl(!!d.locked);})' ..
        '.catch(function(){});' ..
        'setTimeout(_bh,300);' ..
        'var btn=document.getElementById("plb-btn-"+PID);' ..
        'if(btn)btn.addEventListener("click",function(){' ..
        'var nv=!_pl;_spl(nv);' ..
        'fetch("/camera-lock/"+PID,{method:"POST",' ..
        'headers:{"Content-Type":"application/json"},' ..
        'body:JSON.stringify({locked:nv})})' ..
        '.catch(function(){});' ..
        '});' ..
        '})();</script></div>'
      return pandoc.RawBlock("html",
        '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
        lock_toolbar .. '\n' ..
        '<div style="' .. sync_grid .. '">' .. table.concat(sync_cells) .. '</div>\n' ..
        (caption ~= "" and
          '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' .. caption .. '</figcaption>\n'
          or "") ..
        '</figure>\n' .. relay_script)
    end

    -- Independent mode: existing inline-subfigure grid below
    local ncols = tonumber(layout:match("^(%d+)x")) or 1
    local nrows = tonumber(layout:match("x(%d+)$")) or 1

    -- Collect sub-figure cells by reading id1, id2, ... from kwargs
    local cells = {}
    local n = 1
    while true do
      local sub_id_val = kwargs["id" .. n]
      if not sub_id_val then break end
      local sub_id = pandoc.utils.stringify(sub_id_val)
      -- In Quarto's Lua shortcode API, accessing a missing key may return an
      -- empty pandoc element (not nil), so check for empty string too.
      if sub_id == "" then break end
      local fig_path = "state/figures/" .. sub_id .. ".html"
      local exists = io.open(fig_path, "r")
      if exists then exists:close() end
      if exists then
        local cell_iframe
        if _app_mode then
          cell_iframe = '<iframe src="/state/figures/' .. sub_id .. '.html" ' ..
                        'style="width:100%;height:100%;border:none;" frameborder="0"></iframe>'
        else
          local f = io.open(fig_path, "r")
          local content = f:read("*all")
          f:close()
          local escaped = content:gsub("&", "&amp;"):gsub('"', "&quot;")
          cell_iframe = '<iframe srcdoc="' .. escaped .. '" ' ..
                        'style="width:100%;height:100%;border:none;" frameborder="0"></iframe>'
        end
        table.insert(cells, cell_iframe)
      else
        table.insert(cells,
          '<div style="background:#222;display:flex;align-items:center;' ..
          'justify-content:center;color:#888;font-family:sans-serif;font-size:0.85rem;">' ..
          '⚠ ' .. sub_id .. ' not rendered</div>')
      end
      n = n + 1
    end

    if #cells == 0 then
      return pandoc.RawBlock("html",
        '<div style="border:2px dashed #888;padding:1.5rem;text-align:center;' ..
        'border-radius:4px;margin:1rem 0">' ..
        '<strong>⚠ 4D Panel not yet rendered</strong><br>' ..
        'Panel ID: <code>' .. id .. '</code><br>' ..
        '<small>Click <strong>Rebuild HTML</strong> in the dashboard to generate.</small>' ..
        '</div>')
    end

    local grid_style = (
      'display:grid;' ..
      'grid-template-columns:repeat(' .. ncols .. ',1fr);' ..
      'grid-template-rows:repeat(' .. nrows .. ',1fr);' ..
      'gap:4px;width:100%;height:' .. height .. ';background:#111;'
    )

    return pandoc.RawBlock("html",
      '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
      '<div style="' .. grid_style .. '">' .. table.concat(cells) .. '</div>\n' ..
      (caption ~= "" and
        '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' .. caption .. '</figcaption>\n'
        or "") ..
      '</figure>\n' ..
      relay_script)

  -- ── PDF / LaTeX output: LaTeX minipage grid from manifest ─────────────────
  else
    local manifest_path = "state/figures/" .. id .. ".manifest.json"
    local mf = io.open(manifest_path, "r")
    if not mf then
      -- Fallback to composite PNG if manifest missing
      local fig_path = "state/figures/" .. id .. ".png"
      local f2 = io.open(fig_path, "r")
      if f2 then
        f2:close()
        return pandoc.Para({ pandoc.Image(caption, fig_path, id, pandoc.Attr(id, {}, { width = "90%" })) })
      end
      return pandoc.Para({
        pandoc.Str("[Panel "), pandoc.Code(id),
        pandoc.Str(" — run 'Export PDF' from the dashboard to generate this figure]"),
      })
    end
    local manifest_str = mf:read("*all"); mf:close()

    -- Parse subfigure IDs: ["id1","id2",...]
    local subfig_ids = {}
    for s in manifest_str:gmatch('"subfigures"%s*:%s*%[([^%]]*)%]') do
      for sub_id in s:gmatch('"([^"]+)"') do
        table.insert(subfig_ids, sub_id)
      end
    end
    -- Parse column count from layout: "2x1" → ncols=2
    local ncols_str = manifest_str:match('"layout"%s*:%s*"(%d+)x%d+"') or "1"
    local ncols = math.max(1, tonumber(ncols_str) or 1)
    local mp_width = string.format("%.3f", 0.98 / ncols)

    if #subfig_ids == 0 then
      return pandoc.Para({
        pandoc.Str("[Panel "), pandoc.Code(id),
        pandoc.Str(" — manifest empty, run 'Export PDF']"),
      })
    end

    local lines = { "\\begin{figure}[h]\n\\centering\n" }
    for i, sub_id in ipairs(subfig_ids) do
      local pdf_path = "state/figures/" .. sub_id .. ".pdf"
      local png_path = "state/figures/" .. sub_id .. ".png"
      local pf = io.open(pdf_path, "r")
      local fig_src
      if pf then pf:close(); fig_src = pdf_path else fig_src = png_path end
      table.insert(lines, "\\begin{minipage}{" .. mp_width .. "\\textwidth}\n")
      table.insert(lines, "  \\centering\n")
      table.insert(lines, "  \\includegraphics[width=\\linewidth]{" .. fig_src .. "}\n")
      table.insert(lines, "\\end{minipage}")
      local col_pos = (i - 1) % ncols + 1
      local is_last_in_row = col_pos == ncols
      local is_last = i == #subfig_ids
      if not is_last then
        if is_last_in_row then
          table.insert(lines, "\\\\\n")
        else
          table.insert(lines, "\\hfill\n")
        end
      end
    end
    if caption ~= "" then
      table.insert(lines, "\n\\caption{" .. caption .. "}\n")
    end
    table.insert(lines, "\\end{figure}\n")
    return pandoc.RawBlock("latex", table.concat(lines))
  end
end

local function fourd_pvsm(args, kwargs)
  local id      = pandoc.utils.stringify(kwargs["id"]      or pandoc.Str(""))
  local caption = pandoc.utils.stringify(kwargs["caption"] or pandoc.Str(""))

  if id == "" then
    return pandoc.RawBlock("html",
      '<div style="color:red">&#9888; 4d-pvsm: missing required attribute <code>id</code></div>')
  end

  -- HTML output
  if quarto.doc.isFormat("html") then
    -- Paper-view: embed static PNG instead of interactive iframe
    if _paper_view then
      local png_path = "state/figures/" .. id .. ".png"
      local pf = io.open(png_path, "r")
      if pf then pf:close() end
      local cap_html = caption ~= "" and
        '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' ..
        caption .. '</figcaption>\n' or ""
      if not pf then
        return pandoc.RawBlock("html",
          '<figure class="fourd-figure" style="margin:1.5rem 0;">' ..
          '<div style="border:2px dashed #888;padding:1rem;text-align:center;">' ..
          '⚠ PVSM figure <code>' .. id .. '</code> not rendered — click Rebuild HTML</div>' ..
          cap_html .. '</figure>')
      end
      return pandoc.RawBlock("html",
        '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
        '<img src="/state/figures/' .. id .. '.png" style="width:100%;display:block;">\n' ..
        cap_html .. '</figure>')
    end

    local html_path = "state/figures/" .. id .. ".html"
    local exists = io.open(html_path, "r")
    if exists then exists:close() end

    if not exists then
      return pandoc.RawBlock("html",
        '<div style="border:2px dashed #888;padding:1.5rem;text-align:center;' ..
        'border-radius:4px;margin:1rem 0">' ..
        '<strong>&#9888; 4D PVSM figure not yet rendered</strong><br>' ..
        'Figure ID: <code>' .. id .. '</code><br>' ..
        '<small>Click <strong>Rebuild HTML</strong> in the dashboard to generate.</small>' ..
        '</div>')
    end

    local relay_script = ""
    if not _relay_injected then
      _relay_injected = true
      relay_script = _RELAY_SCRIPT
    end

    local cap_html = caption ~= "" and
      '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' .. caption .. '</figcaption>\n'
      or ""

    local body
    if _app_mode then
      -- Camera button at paper level (same as fourd_video) to avoid compositor issues.
      local cam_onclick =
        "(function(){" ..
        "var o=document.getElementById('fourd-cam-overlay');" ..
        "var lb=document.getElementById('fourd-cam-figid');" ..
        "var f=document.getElementById('fourd-cam-iframe');" ..
        "var ss=document.getElementById('fourd-cam-sttxt');" ..
        "if(lb)lb.textContent='fig id: " .. id .. "';" ..
        "if(f)f.src='/state/figures/" .. id .. "-preview.html?t='+Date.now();" ..
        "if(ss){ss.textContent='Rotate - saves automatically';ss.style.color='#0a8';}" ..
        "if(o)o.style.display='flex';" ..
        "})()"
      local iframe_id = 'fourd-pvsm-' .. id
      body = '<div style="position:relative;display:inline-block;width:100%;">' ..
             '<iframe id="' .. iframe_id .. '" src="" width="100%" height="600px" ' ..
             'frameborder="0" style="border:none;border-radius:4px;display:block;"></iframe>' ..
             '<script>(function(){' ..
             'var f=document.getElementById("' .. iframe_id .. '");' ..
             'if(f)f.src="/state/figures/' .. id .. '.html?t="+Date.now();' ..
             '})();</script>' ..
             '<button onclick="' .. cam_onclick .. '" ' ..
             'style="position:absolute;top:8px;right:8px;z-index:10;' ..
             'background:rgba(0,0,0,0.65);color:#fff;border:none;border-radius:4px;' ..
             'padding:4px 10px;font-size:12px;cursor:pointer;">&#128247; Camera View</button>' ..
             '</div>'
    else
      -- Export mode: inline as srcdoc for self-contained HTML
      local f = io.open(html_path, "r")
      local content = f:read("*all")
      f:close()
      local escaped = content:gsub("&", "&amp;"):gsub('"', "&quot;")
      body = '<iframe srcdoc="' .. escaped .. '" width="100%" height="600px" ' ..
             'frameborder="0" style="border:none;border-radius:4px;display:block;"></iframe>'
    end

    return pandoc.RawBlock("html",
      '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
      body .. '\n' .. cap_html ..
      '</figure>\n' ..
      relay_script)

  -- PDF / LaTeX output: embed vector .pdf if available, else .png
  else
    local pdf_path = "state/figures/" .. id .. ".pdf"
    local png_path = "state/figures/" .. id .. ".png"
    local pf = io.open(pdf_path, "r")
    local fig_path
    if pf then
      pf:close()
      fig_path = pdf_path
    else
      local f2 = io.open(png_path, "r")
      if f2 then f2:close(); fig_path = png_path end
    end
    if fig_path then
      local img = pandoc.Image(caption, fig_path, id, pandoc.Attr(id, {}, { width = "90%" }))
      return pandoc.Para({ img })
    else
      return pandoc.Para({
        pandoc.Str("[PVSM figure "),
        pandoc.Code(id),
        pandoc.Str(" - run 'Rebuild HTML' from the dashboard to generate this figure]"),
      })
    end
  end
end

local function fourd_timeseries(args, kwargs)
  local id      = pandoc.utils.stringify(kwargs["id"]      or pandoc.Str(""))
  local caption = pandoc.utils.stringify(kwargs["caption"] or pandoc.Str(""))
  local height  = pandoc.utils.stringify(kwargs["height"]  or pandoc.Str("400px"))

  if id == "" then
    return pandoc.RawBlock("html",
      '<div style="color:red">⚠ 4d-timeseries: missing required attribute <code>id</code></div>')
  end

  if quarto.doc.isFormat("html") then

    -- Paper-view: embed individual subfigure PNGs in a scrollable row so each
    -- cell is readable (the composite PNG would be tiny at 700 px page width).
    if _paper_view then
      local cap_html = caption ~= "" and
        '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' ..
        caption .. '</figcaption>\n' or ""

      -- Try to read the manifest for subfigure IDs
      local manifest_path = "state/figures/" .. id .. ".manifest.json"
      local mf = io.open(manifest_path, "r")
      local subfig_ids = {}
      if mf then
        local ms = mf:read("*all"); mf:close()
        for s in ms:gmatch('"subfigures"%s*:%s*%[([^%]]*)%]') do
          for sub_id in s:gmatch('"([^"]+)"') do
            table.insert(subfig_ids, sub_id)
          end
        end
      end

      if #subfig_ids == 0 then
        -- Fallback: composite PNG (may look small but better than nothing)
        local pf = io.open("state/figures/" .. id .. ".png", "r")
        if pf then pf:close()
          return pandoc.RawBlock("html",
            '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
            '<img src="/state/figures/' .. id .. '.png" style="width:100%;display:block;">\n' ..
            cap_html .. '</figure>')
        end
        return pandoc.RawBlock("html",
          '<figure class="fourd-figure" style="margin:1.5rem 0;">' ..
          '<div style="border:2px dashed #888;padding:1rem;text-align:center;">' ..
          '⚠ Timeseries <code>' .. id .. '</code> not rendered — click Rebuild HTML</div>' ..
          cap_html .. '</figure>')
      end

      -- Build high-fidelity CSS grid (PDF-like)
      local ncols = #subfig_ids
      local imgs = ""
      for _, sub_id in ipairs(subfig_ids) do
        imgs = imgs .. '<img src="/state/figures/' .. sub_id .. '.png" style="width:100%;display:block;">\n'
      end
      local grid_style = 'display:grid;grid-template-columns:repeat(' .. ncols .. ',1fr);gap:4px;width:100%;background:white;'
      return pandoc.RawBlock("html",
        '<figure class="fourd-figure" style="margin:1.5rem 0;background:white;padding:10px;border-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,0.05);">\n' ..
        '<div style="' .. grid_style .. '">' .. imgs .. '</div>\n' ..
        cap_html .. '</figure>')
    end

    -- Timeseries is always sync — read manifest to get subfigure IDs, then embed
    -- each as a direct srcdoc iframe with data-panel attribute.
    -- Avoids data:text/html;base64 iframes which break vtk.js WebGL rendering.
    local manifest_path = "state/figures/" .. id .. ".manifest.json"
    local mf = io.open(manifest_path, "r")
    if not mf then
      return pandoc.RawBlock("html",
        '<div style="border:2px dashed #888;padding:1.5rem;text-align:center;">' ..
        '⚠ 4D Timeseries <code>' .. id .. '</code> not yet rendered — ' ..
        'click <strong>Rebuild HTML</strong> in the dashboard.</div>')
    end
    local manifest_str = mf:read("*all"); mf:close()

    -- Simple JSON array parse for "subfigures": ["a","b",...]
    local subfig_ids = {}
    for s in manifest_str:gmatch('"subfigures"%s*:%s*%[([^%]]*)%]') do
      for sub_id in s:gmatch('"([^"]+)"') do
        table.insert(subfig_ids, sub_id)
      end
    end
    -- Layout: Nx1 where N = number of subfigures
    local ncols = math.max(1, #subfig_ids)

    local relay_script = ""
    if not _relay_injected then
      _relay_injected = true
      relay_script = _RELAY_SCRIPT
    end

    if #subfig_ids == 0 then
      return pandoc.RawBlock("html",
        '<div style="border:2px dashed #888;padding:1.5rem;text-align:center;">' ..
        '⚠ 4D Timeseries <code>' .. id .. '</code> manifest empty — ' ..
        'click <strong>Rebuild HTML</strong> in the dashboard.</div>')
    end

    local ts_cells = {}
    for _, sub_id in ipairs(subfig_ids) do
      local fig_path = "state/figures/" .. sub_id .. ".html"
      local cell_iframe
      if _app_mode then
        cell_iframe = '<iframe src="/state/figures/' .. sub_id .. '.html" ' ..
                      'data-panel="' .. id .. '" ' ..
                      'style="width:100%;height:100%;border:none;" frameborder="0"></iframe>'
      else
        local fh = io.open(fig_path, "r")
        if fh then
          local content = fh:read("*all"); fh:close()
          -- Hide per-frame topbars by injecting CSS
          local with_topbar_css = content:gsub(
            '</head>',
            '<style>#cs-topbar-__FIGSAFE__{display:none!important;}div[id^="cs-topbar"]{display:none!important;}</style></head>'
          )
          local escaped = with_topbar_css:gsub("&", "&amp;"):gsub('"', "&quot;")
          cell_iframe = '<iframe srcdoc="' .. escaped .. '" ' ..
                        'data-panel="' .. id .. '" ' ..
                        'style="width:100%;height:100%;border:none;" frameborder="0"></iframe>'
        else
          cell_iframe = '<div style="background:#222;display:flex;align-items:center;' ..
                        'justify-content:center;color:#888;font-family:sans-serif;font-size:0.85rem;">' ..
                        '⚠ ' .. sub_id .. ' not rendered</div>'
        end
      end
      table.insert(ts_cells, cell_iframe)
    end

    local grid_style = 'display:grid;grid-template-columns:repeat(' .. ncols .. ',1fr);' ..
                       'grid-template-rows:1fr;gap:4px;' ..
                       'width:100%;height:' .. height .. ';background:white;'
    local lock_toolbar_ts = '<div id="plb-' .. id .. '" style="' ..
      'display:flex;align-items:center;gap:8px;background:white;' ..
      'border-bottom:1px solid #e0e0e0;padding:8px;' ..
      'font-family:system-ui,sans-serif;font-size:12px;">' ..
      '<button id="plb-btn-' .. id .. '" style="background:none;border:none;' ..
      'cursor:pointer;font-size:14px;padding:0;line-height:1;">&#x1F513;</button>' ..
      '<script>(function(){' ..
      'var PID="' .. id .. '";var _pl=false;' ..
      'function _bc(v){var f=document.querySelectorAll(' ..
      '"iframe[data-panel=\\""+PID+"\\"]");' ..
      'for(var i=0;i<f.length;i++)f[i].contentWindow.postMessage({type:"4dpaper-lock-all",locked:v},"*");}' ..
      'function _bh(){var f=document.querySelectorAll(' ..
      '"iframe[data-panel=\\""+PID+"\\"]");' ..
      'for(var i=0;i<f.length;i++)f[i].contentWindow.postMessage({type:"4dpaper-hide-lock-btn"},"*");}' ..
      'function _spl(v){_pl=v;' ..
      'var b=document.getElementById("plb-btn-"+PID);' ..
      'if(b)b.innerHTML=v?"&#x1F512;":"&#x1F513;";' ..
      '_bc(v);}' ..
      'fetch("/camera-lock/"+PID)' ..
      '.then(function(r){return r.json();})' ..
      '.then(function(d){_spl(!!d.locked);})' ..
      '.catch(function(){});' ..
      'setTimeout(_bh,300);' ..
      'var btn=document.getElementById("plb-btn-"+PID);' ..
      'if(btn)btn.addEventListener("click",function(){' ..
      'var nv=!_pl;_spl(nv);' ..
      'fetch("/camera-lock/"+PID,{method:"POST",' ..
      'headers:{"Content-Type":"application/json"},' ..
      'body:JSON.stringify({locked:nv})})' ..
      '.catch(function(){});' ..
      '});' ..
      '})();</script></div>'
    return pandoc.RawBlock("html",
      '<figure class="fourd-figure" style="margin:1.5rem 0;background:white;padding:0;border-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,0.05);">\n' ..
      lock_toolbar_ts .. '\n' ..
      '<div style="' .. grid_style .. '">' .. table.concat(ts_cells) .. '</div>\n' ..
      (caption ~= "" and
        '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' .. caption .. '</figcaption>\n'
        or "") ..
      '</figure>\n' .. relay_script)

  else
    -- PDF: LaTeX minipage grid — timeseries is always Nx1, read manifest for IDs
    local manifest_path = "state/figures/" .. id .. ".manifest.json"
    local mf = io.open(manifest_path, "r")
    if not mf then
      -- Fallback to composite PNG
      local fig_path = "state/figures/" .. id .. ".png"
      local f2 = io.open(fig_path, "r")
      if f2 then
        f2:close()
        return pandoc.Para({ pandoc.Image(caption, fig_path, id, pandoc.Attr(id, {}, { width = "90%" })) })
      end
      return pandoc.Para({
        pandoc.Str("[Timeseries "), pandoc.Code(id),
        pandoc.Str(" — run 'Export PDF' from the dashboard to generate this figure]"),
      })
    end
    local manifest_str = mf:read("*all"); mf:close()

    local subfig_ids = {}
    for s in manifest_str:gmatch('"subfigures"%s*:%s*%[([^%]]*)%]') do
      for sub_id in s:gmatch('"([^"]+)"') do
        table.insert(subfig_ids, sub_id)
      end
    end
    local ncols = math.max(1, #subfig_ids)
    local mp_width = string.format("%.3f", 0.98 / ncols)

    if #subfig_ids == 0 then
      return pandoc.Para({
        pandoc.Str("[Timeseries "), pandoc.Code(id),
        pandoc.Str(" — manifest empty, run 'Export PDF']"),
      })
    end

    local lines = { "\\begin{figure}[h]\n\\centering\n" }
    for i, sub_id in ipairs(subfig_ids) do
      local pdf_path = "state/figures/" .. sub_id .. ".pdf"
      local png_path = "state/figures/" .. sub_id .. ".png"
      local pf = io.open(pdf_path, "r")
      local fig_src
      if pf then pf:close(); fig_src = pdf_path else fig_src = png_path end
      table.insert(lines, "\\begin{minipage}{" .. mp_width .. "\\textwidth}\n")
      table.insert(lines, "  \\centering\n")
      table.insert(lines, "  \\includegraphics[width=\\linewidth]{" .. fig_src .. "}\n")
      table.insert(lines, "\\end{minipage}")
      if i < #subfig_ids then
        table.insert(lines, "\\hfill\n")
      end
    end
    if caption ~= "" then
      table.insert(lines, "\n\\caption{" .. caption .. "}\n")
    end
    table.insert(lines, "\\end{figure}\n")
    return pandoc.RawBlock("latex", table.concat(lines))
  end
end

local function fourd_graph(args, kwargs)
  local id      = pandoc.utils.stringify(kwargs["id"]      or pandoc.Str(""))
  local caption = pandoc.utils.stringify(kwargs["caption"] or pandoc.Str(""))

  if id == "" then
    return pandoc.RawBlock("html",
      '<div style="color:red">⚠ 4d-graph: missing required attribute <code>id</code></div>')
  end

  if quarto.doc.isFormat("html") then
    -- Paper-view: embed static PNG instead of interactive iframe
    if _paper_view then
      local png_path = "state/figures/" .. id .. ".png"
      local pf = io.open(png_path, "r")
      if pf then pf:close() end
      local cap_html = caption ~= "" and
        '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' ..
        caption .. '</figcaption>\n' or ""
      if not pf then
        return pandoc.RawBlock("html",
          '<figure class="fourd-figure" style="margin:1.5rem 0;">' ..
          '<div style="border:2px dashed #888;padding:1rem;text-align:center;">' ..
          '⚠ Graph <code>' .. id .. '</code> not rendered — click Rebuild HTML</div>' ..
          cap_html .. '</figure>')
      end
      return pandoc.RawBlock("html",
        '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
        '<img src="/state/figures/' .. id .. '.png" style="width:100%;display:block;">\n' ..
        cap_html .. '</figure>')
    end

    local html_path = "state/figures/" .. id .. ".html"
    local exists = io.open(html_path, "r")
    if exists then exists:close() end

    if not exists then
      return pandoc.RawBlock("html",
        '<div style="border:2px dashed #888;padding:1.5rem;text-align:center;' ..
        'border-radius:4px;margin:1rem 0">' ..
        '<strong>⚠ 4D Graph not yet rendered</strong><br>' ..
        'Figure ID: <code>' .. id .. '</code><br>' ..
        '<small>Click <strong>Rebuild HTML</strong> in the dashboard to generate.</small>' ..
        '</div>')
    end

    local cap_html = caption ~= "" and
      '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' .. caption .. '</figcaption>\n'
      or ""

    local body
    if _app_mode then
      body = '<iframe src="/state/figures/' .. id .. '.html" width="100%" height="600px" ' ..
             'frameborder="0" style="border:none;border-radius:4px;display:block;"></iframe>'
    else
      local f = io.open(html_path, "r")
      local content = f:read("*all")
      f:close()
      local escaped = content:gsub("&", "&amp;"):gsub('"', "&quot;")
      body = '<iframe srcdoc="' .. escaped .. '" width="100%" height="600px" ' ..
             'frameborder="0" style="border:none;border-radius:4px;display:block;"></iframe>'
    end

    local relay_script = ""
    if not _relay_injected then
      _relay_injected = true
      relay_script = _RELAY_SCRIPT
    end

    return pandoc.RawBlock("html",
      relay_script ..
      '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
      body .. '\n' .. cap_html ..
      '</figure>\n')

  -- PDF / LaTeX output
  else
    local pdf_path = "state/figures/" .. id .. ".pdf"
    local png_path = "state/figures/" .. id .. ".png"
    local pf = io.open(pdf_path, "r")
    local fig_path
    if pf then
      pf:close()
      fig_path = pdf_path
    else
      local f2 = io.open(png_path, "r")
      if f2 then f2:close(); fig_path = png_path end
    end
    if fig_path then
      local img = pandoc.Image(caption, fig_path, id, pandoc.Attr(id, {}, { width = "90%" }))
      return pandoc.Para({ img })
    else
      return pandoc.Para({
        pandoc.Str("[Graph "),
        pandoc.Code(id),
        pandoc.Str(" - run 'Rebuild HTML' from the dashboard to generate this figure]"),
      })
    end
  end
end

return {
  ["4d-image"]      = fourd_image,
  ["4d-video"]      = fourd_video,
  ["4d-panel"]      = fourd_panel,
  ["4d-pvsm"]       = fourd_pvsm,
  ["4d-timeseries"] = fourd_timeseries,
  ["4d-graph"]      = fourd_graph,
}
