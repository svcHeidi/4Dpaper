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

-- ── Shared relay script (injected once per page) ──────────────────────────
-- Handles two concerns:
--  1. Camera overlay: position:fixed inside THIS document (analysis_report.html).
--     The overlay covers the full paper-preview pane — no cross-frame DOM injection.
--  2. Figure message relay: handles camera/field messages from child iframes.
local _RELAY_SCRIPT = [=[
<script>
(function(){
  /* ── Debug bar: shows message chain status without DevTools ─────── */
  (function(){
    if (document.getElementById('fourd-dbg')) return;
    var d=document.createElement('div');
    d.id='fourd-dbg';
    d.style.cssText='position:fixed;bottom:4px;right:4px;z-index:2147483646;'+
      'background:rgba(0,0,0,0.82);color:#0f0;font-size:10px;font-family:monospace;'+
      'padding:4px 8px;border-radius:4px;max-width:320px;pointer-events:none;';
    d.textContent='[4d] relay ready';
    document.body.appendChild(d);
  })();
  function _dbg(msg){
    var d=document.getElementById('fourd-dbg');
    if(d)d.textContent='[4d] '+msg;
    console.log('[4dpaper]',msg);
  }

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
      var figId=e.data.fig_id;
      var _f2=document.getElementById('fourd-cam-iframe');
      var _ss2=document.getElementById('fourd-cam-sttxt');
      fetch('/camera/'+figId,{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(e.data.camera)
      }).then(function(r){
        if(_ss2){
          if(r.ok){_ss2.textContent='\u2713 Camera saved \u2014 click \u201cRebuild HTML\u201d to apply';_ss2.style.color='#4caf50';}
          else{_ss2.textContent='\u2717 Save failed (server error)';_ss2.style.color='#f44336';}
        }
        var ack={type:'4dpaper-camera-ack',fig_id:figId,status:r.ok?'ok':'error'};
        if(_f2&&_f2.contentWindow)_f2.contentWindow.postMessage(ack,'*');
        if(e.source&&e.source!==(_f2&&_f2.contentWindow))e.source.postMessage(ack,'*');
      }).catch(function(){
        if(_ss2){_ss2.textContent='\u2717 Save failed (network error)';_ss2.style.color='#f44336';}
        var ack={type:'4dpaper-camera-ack',fig_id:figId,status:'error'};
        if(_f2&&_f2.contentWindow)_f2.contentWindow.postMessage(ack,'*');
        if(e.source&&e.source!==(_f2&&_f2.contentWindow))e.source.postMessage(ack,'*');
      });

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

    -- ── PDF / LaTeX output: embed pre-rendered PNG ────────────────────────────
  else
    local fig_path = "state/figures/" .. id .. ".png"
    local f = io.open(fig_path, "r")
    if f then
      f:close()
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
    -- Inject relay script once per page
    local relay_script = ""
    if not _relay_injected then
      _relay_injected = true
      relay_script = _RELAY_SCRIPT
    end

    if camera_mode == "sync" then
      -- Sync mode: embed composite HTML as single iframe so sync re_relay executes.
      local composite_path = "state/figures/" .. id .. ".html"
      local f = io.open(composite_path, "r")
      if not f then
        return pandoc.RawBlock("html",
          '<div style="border:2px dashed #888;padding:1.5rem;text-align:center;">' ..
          '⚠ 4D Panel <code>' .. id .. '</code> not yet rendered — ' ..
          'click <strong>Rebuild HTML</strong> in the dashboard.</div>')
      end
      local composite_iframe
      if _app_mode then
        f:close()
        composite_iframe = '<iframe src="/state/figures/' .. id .. '.html" ' ..
                           'style="width:100%;height:' .. height .. ';border:none;" frameborder="0"></iframe>'
      else
        local content = f:read("*all"); f:close()
        local escaped = content:gsub("&", "&amp;"):gsub('"', "&quot;")
        composite_iframe = '<iframe srcdoc="' .. escaped .. '" ' ..
                           'style="width:100%;height:' .. height .. ';border:none;" frameborder="0"></iframe>'
      end
      return pandoc.RawBlock("html",
        '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
        composite_iframe .. '\n' ..
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

  -- ── PDF / LaTeX output: embed composite PNG ───────────────────────────────
  else
    local fig_path = "state/figures/" .. id .. ".png"
    local f = io.open(fig_path, "r")
    if f then
      f:close()
      local img = pandoc.Image(caption, fig_path, id, pandoc.Attr(id, {}, { width = "90%" }))
      return pandoc.Para({ img })
    else
      return pandoc.Para({
        pandoc.Str("[Panel "),
        pandoc.Code(id),
        pandoc.Str(" — run 'Export PDF' from the dashboard to generate this figure]"),
      })
    end
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

  -- PDF / LaTeX output
  else
    local fig_path = "state/figures/" .. id .. ".png"
    local f = io.open(fig_path, "r")
    if f then
      f:close()
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

return {
  ["4d-image"] = fourd_image,
  ["4d-video"] = fourd_video,
  ["4d-panel"] = fourd_panel,
  ["4d-pvsm"]  = fourd_pvsm,
}
