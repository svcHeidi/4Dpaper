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
      relay_script = [[
<script>
(function(){
  window.addEventListener("message",function(e){
    if(!e.data)return;
    if(e.data.type==="4dpaper-camera"){
      var figId=e.data.fig_id;
      var camera=e.data.camera;
      fetch("/camera/"+figId,{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify(camera)
      }).then(function(r){
        if(r.ok&&e.source){
          e.source.postMessage({type:"4dpaper-camera-ack",fig_id:figId,status:"ok"},"*");
        }
      }).catch(function(){
        if(e.source){
          e.source.postMessage({type:"4dpaper-camera-ack",fig_id:figId,status:"error"},"*");
        }
      });
    } else if(e.data.type==="4dpaper-field-update"){
      var figId=e.data.fig_id;
      var payload=e.data.data;
      fetch("/field/"+figId,{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify(payload)
      }).then(function(r){
        if(r.ok&&e.source){
          e.source.postMessage({type:"4dpaper-field-ack",fig_id:figId,status:"ok"},"*");
        }
      }).catch(function(){
        if(e.source){
          e.source.postMessage({type:"4dpaper-field-ack",fig_id:figId,status:"error"},"*");
        }
      });
    }
  });
})();
</script>
]]
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
      relay_script = [[
<script>
(function(){
  window.addEventListener("message",function(e){
    if(!e.data)return;
    if(e.data.type==="4dpaper-camera"){
      var figId=e.data.fig_id;
      var camera=e.data.camera;
      fetch("/camera/"+figId,{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify(camera)
      }).then(function(r){
        if(r.ok&&e.source){
          e.source.postMessage({type:"4dpaper-camera-ack",fig_id:figId,status:"ok"},"*");
        }
      }).catch(function(){
        if(e.source){
          e.source.postMessage({type:"4dpaper-camera-ack",fig_id:figId,status:"error"},"*");
        }
      });
    } else if(e.data.type==="4dpaper-field-update"){
      var figId=e.data.fig_id;
      var payload=e.data.data;
      fetch("/field/"+figId,{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify(payload)
      }).then(function(r){
        if(r.ok&&e.source){
          e.source.postMessage({type:"4dpaper-field-ack",fig_id:figId,status:"ok"},"*");
        }
      }).catch(function(){
        if(e.source){
          e.source.postMessage({type:"4dpaper-field-ack",fig_id:figId,status:"error"},"*");
        }
      });
    }
  });
})();
</script>
]]
    end

    local cap_html = caption ~= "" and
      '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' .. caption .. '</figcaption>\n'
      or ""

    local body
    if _app_mode then
      body = '<iframe src="/state/figures/' .. id .. '-video.html" width="100%" height="600px" ' ..
             'frameborder="0" style="border:none;border-radius:4px;display:block;"></iframe>'
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

  if id == "" then
    return pandoc.RawBlock("html",
      '<div style="color:red">⚠ 4d-panel: missing required attribute <code>id</code></div>')
  end

  -- ── HTML output: CSS grid of individual srcdoc iframes ────────────────────
  -- Each sub-figure is a direct srcdoc iframe (same depth as fourd_image).
  -- This avoids triple-nesting (page → composite srcdoc → data: iframe).
  if quarto.doc.isFormat("html") then
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

    -- Inject relay script once per page (shared guard with fourd_image/fourd_video)
    local relay_script = ""
    if not _relay_injected then
      _relay_injected = true
      relay_script = [[
<script>
(function(){
  window.addEventListener("message",function(e){
    if(!e.data)return;
    if(e.data.type==="4dpaper-camera"){
      var figId=e.data.fig_id;
      var camera=e.data.camera;
      fetch("/camera/"+figId,{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify(camera)
      }).then(function(r){
        if(r.ok&&e.source){
          e.source.postMessage({type:"4dpaper-camera-ack",fig_id:figId,status:"ok"},"*");
        }
      }).catch(function(){
        if(e.source){
          e.source.postMessage({type:"4dpaper-camera-ack",fig_id:figId,status:"error"},"*");
        }
      });
    } else if(e.data.type==="4dpaper-field-update"){
      var figId=e.data.fig_id;
      var payload=e.data.data;
      fetch("/field/"+figId,{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify(payload)
      }).then(function(r){
        if(r.ok&&e.source){
          e.source.postMessage({type:"4dpaper-field-ack",fig_id:figId,status:"ok"},"*");
        }
      }).catch(function(){
        if(e.source){
          e.source.postMessage({type:"4dpaper-field-ack",fig_id:figId,status:"error"},"*");
        }
      });
    }
  });
})();
</script>
]]
    end

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

return {
  ["4d-image"] = fourd_image,
  ["4d-video"] = fourd_video,
  ["4d-panel"] = fourd_panel,
}
