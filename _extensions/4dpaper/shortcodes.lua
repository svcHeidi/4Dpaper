--[[
4DPaper shortcode handler.

Usage in .qmd:
  {{< 4d-image src="case.foam" field="Vm" id="fig-vm" >}}
  {{< 4d-image src="case.foam" field="activationTime" id="fig-at" time="last" caption="Activation time" >}}

HTML output: embeds state/figures/<id>.html as raw HTML block (interactive vtk.js)
PDF output:  embeds state/figures/<id>.png as a standard Markdown image
--]]

local _relay_injected = false
local _panel_toolbar_style_injected = false
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
      if(panelId){
        var liveFrames=document.querySelectorAll('iframe[data-panel="'+panelId+'"]');
        for(var _pl=0;_pl<liveFrames.length;_pl++){
          if(liveFrames[_pl].contentWindow !== e.source) {
            liveFrames[_pl].contentWindow.postMessage({type:'4dpaper-camera-apply',camera:e.data.camera},'*');
          }
        }
      }
      fetch('/camera/'+camId,{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(e.data.camera)
      }).catch(function(){});

      if(panelId){
        var ack={type:'4dpaper-camera-ack',fig_id:'*',status:'ok'};
        var pFrames=document.querySelectorAll('iframe[data-panel="'+panelId+'"]');
        for(var _pj=0;_pj<pFrames.length;_pj++){
          pFrames[_pj].contentWindow.postMessage(ack,'*');
        }
      } else {
        var ack2={type:'4dpaper-camera-ack',fig_id:camId,status:'ok'};
        if(_f2&&_f2.contentWindow)_f2.contentWindow.postMessage(ack2,'*');
        if(e.source&&e.source!==(_f2&&_f2.contentWindow))e.source.postMessage(ack2,'*');
      }

    } else if(e.data.type==="4dpaper-time"){
      var timePanelId=null;
      var timePanelFrames=document.querySelectorAll("iframe[data-panel]");
      for(var _ti=0;_ti<timePanelFrames.length;_ti++){
        if(timePanelFrames[_ti].contentWindow===e.source){
          timePanelId=timePanelFrames[_ti].getAttribute("data-panel");break;
        }
      }
      var timeSyncEnabled = false;
      if(timePanelId){
        var timeSourceFrame = null;
        for(var _tf=0;_tf<timePanelFrames.length;_tf++){
          if(timePanelFrames[_tf].contentWindow===e.source){
            timeSourceFrame=timePanelFrames[_tf];
            timeSyncEnabled=timeSourceFrame.getAttribute("data-panel-time-sync")==="true";
            break;
          }
        }
      }
      if(timePanelId && timeSyncEnabled){
        var syncFrames=document.querySelectorAll('iframe[data-panel="'+timePanelId+'"]');
        var sourceIdx=(e.data.source_idx!=null?e.data.source_idx:e.data.idx);
        for(var _tj=0;_tj<syncFrames.length;_tj++){
          if(syncFrames[_tj].contentWindow!==e.source){
            syncFrames[_tj].contentWindow.postMessage(
              {type:"4dpaper-time-apply",fig_id:timePanelId,idx:e.data.idx,source_idx:sourceIdx,playing:!!e.data.playing},
              "*"
            );
          }
        }
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

local function _count_time_frames_from_html(path)
  local fh = io.open(path, "r")
  if not fh then return 0 end
  local html = fh:read("*all")
  fh:close()
  local labels = html:match("TIME_LABELS%s*=%s*(%b[])")
  if not labels then return 0 end
  local n = 0
  for _ in labels:gmatch('"[^"]*"') do
    n = n + 1
  end
  return n
end

local function _infer_panel_frame_count(subfig_ids)
  local nmax = 0
  for _, sub_id in ipairs(subfig_ids) do
    local n = _count_time_frames_from_html("state/figures/" .. sub_id .. ".html")
    if n > nmax then nmax = n end
  end
  return nmax
end

local function _manifest_time_indices(manifest_str)
  local indices = {}
  local raw = manifest_str:match('"time_indices"%s*:%s*(%b[])')
  if not raw then return indices end
  for num in raw:gmatch('%-?%d+') do
    table.insert(indices, tonumber(num))
  end
  return indices
end

local function _panel_toolbar_html(id, frame_count, time_indices, show_transport)
  if show_transport == nil then
    show_transport = true
  end
  local toolbar_style = ""
  if not _panel_toolbar_style_injected then
    _panel_toolbar_style_injected = true
    toolbar_style = [[
<style>
.plb-toolbar{
  display:flex;
  align-items:center;
  justify-content:flex-end;
  gap:8px;
  min-height:26px;
  padding:0 8px;
  background:rgba(18,18,26,0.82);
  border-bottom:1px solid rgba(255,255,255,0.09);
  font-family:system-ui,sans-serif;
  font-size:11px;
}
.plb-transport{
  display:flex;
  align-items:center;
  gap:6px;
  min-width:220px;
  flex:1;
}
.plb-play,
.plb-lock{
  background:none;
  border:none;
  color:#ccc;
  cursor:pointer;
  line-height:1;
}
.plb-play{
  flex-shrink:0;
  padding:0 1px;
  font-size:11px;
}
.plb-lock{
  flex-shrink:0;
  padding:0 2px;
  font-size:12px;
}
</style>
]]
  end
  local actual = time_indices or {}
  local transport_count = #actual > 0 and #actual or frame_count
  local transport = ""
  local actual_json = "[]"
  if show_transport and transport_count > 1 then
    actual_json = "[" .. table.concat(actual, ",") .. "]"
    transport =
      '<div class="plb-transport">' ..
      '<button id="plb-play-' .. id .. '" class="plb-play" title="Play / pause synchronized animation">&#x25B6;</button>' ..
      '</div>'
  else
    actual_json = "[]"
  end
  return toolbar_style ..
    '<div id="plb-' .. id .. '" class="plb-toolbar">' ..
    transport ..
    '<button id="plb-btn-' .. id .. '" class="plb-lock" title="Lock / unlock panel cameras">&#x1F513;</button>' ..
    '<script>(function(){' ..
    'var PID="' .. id .. '",N=' .. transport_count .. ',ACTUAL=' .. actual_json .. ',_pl=false,_idx=0,_tm=0;' ..
    'function _fs(){return document.querySelectorAll("iframe[data-panel=\\""+PID+"\\"]");}' ..
    'function _bc(v){var f=_fs();for(var i=0;i<f.length;i++)f[i].contentWindow.postMessage({type:"4dpaper-lock-all",locked:v},"*");}' ..
    'function _bh(){var f=_fs();for(var i=0;i<f.length;i++)f[i].contentWindow.postMessage({type:"4dpaper-hide-lock-btn"},"*");}' ..
    'function _actual(i){return ACTUAL.length?ACTUAL[i]:i;}' ..
    'function _fromActual(i){if(!ACTUAL.length)return i;var best=0,bestDiff=Math.abs(ACTUAL[0]-i);for(var j=1;j<ACTUAL.length;j++){var d=Math.abs(ACTUAL[j]-i);if(d<bestDiff){best=j;bestDiff=d;}}return best;}' ..
    'function _send(i){var actual=_actual(i);var f=_fs();for(var j=0;j<f.length;j++)f[j].contentWindow.postMessage({type:"4dpaper-time-apply",fig_id:PID,idx:i,source_idx:actual,playing:false},"*");}' ..
    'function _ui(i){if(N<2)return;_idx=Math.max(0,Math.min(parseInt(i||0,10)||0,N-1));}' ..
    'function _seek(i){_ui(i);_send(_idx);}' ..
    'function _play(v){if(N<2)return;_pl=!!v;var b=document.getElementById("plb-play-"+PID);if(b)b.innerHTML=_pl?"&#x23F8;":"&#x25B6;";if(_tm){clearInterval(_tm);_tm=0;}if(_pl){_seek(_idx);_tm=setInterval(function(){_seek((_idx+1)%N);},180);}}' ..
    'var pb=document.getElementById("plb-play-"+PID);if(pb)pb.addEventListener("click",function(){_play(!_pl);});' ..
    'window.addEventListener("message",function(e){if(!e.data||e.data.type!=="4dpaper-time")return;var v=e.data.source_idx!=null?e.data.source_idx:e.data.idx;_ui(_fromActual(parseInt(v||0,10)||0));});' ..
    'var _locked=false;' ..
    'function _spl(v){_locked=v;var b=document.getElementById("plb-btn-"+PID);if(b)b.innerHTML=v?"&#x1F512;":"&#x1F513;";_bc(v);}' ..
    'fetch("/camera-lock/"+PID).then(function(r){return r.json();}).then(function(d){_spl(!!d.locked);}).catch(function(){});' ..
    'var _iv=setInterval(_bh,500); setTimeout(function(){clearInterval(_iv);},8000);' ..
    'var btn=document.getElementById("plb-btn-"+PID);if(btn)btn.addEventListener("click",function(){var nv=!_locked;_spl(nv);fetch("/camera-lock/"+PID,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({locked:nv})}).catch(function(){});});' ..
    '})();</script></div>'
end

local function _shared_relay_script_once()
  if _relay_injected then
    return ""
  end
  _relay_injected = true
  return _RELAY_SCRIPT
end

local function _build_sync_iframe_panel(id, caption, height, ncols, nrows, subfig_ids, show_transport, time_indices)
  if #subfig_ids == 0 then
    return nil
  end

  local cells = {}
  for _, sub_id in ipairs(subfig_ids) do
    local fig_path = "state/figures/" .. sub_id .. ".html"
    local exists = io.open(fig_path, "r")
    if exists then exists:close() end

    if exists then
      local cell_iframe
      if _app_mode then
        cell_iframe = '<iframe src="/state/figures/' .. sub_id .. '.html" ' ..
                      'data-panel="' .. id .. '" ' ..
                      'style="width:100%;height:100%;border:none;" frameborder="0"></iframe>'
      else
        cell_iframe = '<iframe data-fourd-inject="state/figures/' .. sub_id .. '.html" ' ..
                      'data-panel="' .. id .. '" ' ..
                      'style="width:100%;height:100%;border:none;" frameborder="0"></iframe>'
      end
      table.insert(cells, cell_iframe)
    else
      table.insert(cells,
        '<div style="background:#222;display:flex;align-items:center;' ..
        'justify-content:center;color:#888;font-family:sans-serif;font-size:0.85rem;">' ..
        '⚠ ' .. sub_id .. ' not rendered</div>')
    end
  end

  local grid_style = 'display:grid;grid-template-columns:repeat(' .. ncols .. ',1fr);' ..
                     'grid-template-rows:repeat(' .. nrows .. ',1fr);gap:4px;' ..
                     'width:100%;height:' .. height .. ';background:#111;'
  local toolbar = _panel_toolbar_html(
    id,
    _infer_panel_frame_count(subfig_ids),
    time_indices,
    show_transport
  )
  local relay_script = _shared_relay_script_once()

  return pandoc.RawBlock("html",
    '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
    toolbar .. '\n' ..
    '<div style="' .. grid_style .. '">' .. table.concat(cells) .. '</div>\n' ..
    (caption ~= "" and
      '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' .. caption .. '</figcaption>\n'
      or "") ..
    '</figure>\n' .. relay_script)
end

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
      -- Export mode: output a placeholder for the Python post-processor to inject the massive Base64 strings.
      -- This bypasses Pandoc's extremely slow embed-resources step.
      iframe = '<iframe data-fourd-inject="state/figures/' .. id .. '.html" width="100%" height="600px" ' ..
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

    if camera_mode == "sync" then
      -- Sync mode: share the same iframe wrapper/relay path used by timeseries.
      local ncols_s = layout:match("^(%d+)x") or "1"
      local nrows_s = layout:match("x(%d+)$") or "1"
      local ncols = tonumber(ncols_s) or 1
      local nrows = tonumber(nrows_s) or 1
      local sync_ids = {}
      local n = 1
      while true do
        local sub_id_val = kwargs["id" .. n]
        if not sub_id_val then break end
        local sub_id = pandoc.utils.stringify(sub_id_val)
        if sub_id == "" then break end
        table.insert(sync_ids, sub_id)
        n = n + 1
      end
      if #sync_ids == 0 then
        return pandoc.RawBlock("html",
          '<div style="border:2px dashed #888;padding:1.5rem;text-align:center;">' ..
          '⚠ 4D Panel <code>' .. id .. '</code> not yet rendered — ' ..
          'click <strong>Rebuild HTML</strong> in the dashboard.</div>')
      end
      return _build_sync_iframe_panel(id, caption, height, ncols, nrows, sync_ids, true, nil)
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
          cell_iframe = '<iframe data-fourd-inject="state/figures/' .. sub_id .. '.html" ' ..
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
      -- Export mode: output a placeholder for Python injection
      body = '<iframe data-fourd-inject="state/figures/' .. id .. '.html" width="100%" height="600px" ' ..
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

    -- Read manifest to get subfigure IDs, render as sync panel (lock toolbar + grid)
    local manifest_path = "state/figures/" .. id .. ".manifest.json"
    local mf = io.open(manifest_path, "r")
    if not mf then
      return pandoc.RawBlock("html",
        '<div style="border:2px dashed #888;padding:1.5rem;text-align:center;">' ..
        '⚠ 4D Timeseries <code>' .. id .. '</code> not yet rendered — ' ..
        'click <strong>Rebuild HTML</strong> in the dashboard.</div>')
    end
    local manifest_str = mf:read("*all"); mf:close()

    -- Parse subfigures and layout
    local subfig_ids = {}
    for s in manifest_str:gmatch('"subfigures"%s*:%s*%[([^%]]*)%]') do
      for sub_id in s:gmatch('"([^"]+)"') do
        table.insert(subfig_ids, sub_id)
      end
    end
    local ncols = math.max(1, #subfig_ids)
    local time_indices = _manifest_time_indices(manifest_str)

    if #subfig_ids == 0 then
      return pandoc.RawBlock("html",
        '<div style="border:2px dashed #888;padding:1.5rem;text-align:center;">' ..
        '⚠ 4D Timeseries <code>' .. id .. '</code> manifest empty — ' ..
        'click <strong>Rebuild HTML</strong> in the dashboard.</div>')
    end

    -- Reuse the exact same sync-panel iframe/relay wrapper as 4d-panel, but
    -- disable the parent transport so each child frame keeps its own timeline.
    return _build_sync_iframe_panel(id, caption, height, ncols, 1, subfig_ids, false, time_indices)

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
      body = '<iframe data-fourd-inject="state/figures/' .. id .. '.html" width="100%" height="600px" ' ..
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

-- 4d-multi-image: multiple datasets in one interactive scene.
-- The Python pre-render hook generates state/figures/<id>.html (and .png).
-- From Lua's perspective the output is identical to 4d-image — just embed it.
local fourd_multi_image = fourd_image

return {
  ["4d-image"]       = fourd_image,
  ["4d-multi-image"] = fourd_multi_image,
  ["4d-video"]       = fourd_video,
  ["4d-panel"]       = fourd_panel,
  ["4d-pvsm"]        = fourd_pvsm,
  ["4d-timeseries"]  = fourd_timeseries,
  ["4d-graph"]       = fourd_graph,
}
