--[[
4DPaper shortcode handler.

Usage in .qmd:
  {{< 4d-image src="case.foam" field="Vm" id="fig-vm" >}}
  {{< 4d-image src="case.foam" field="activationTime" id="fig-at" time="last" caption="Activation time" >}}

HTML output: embeds state/figures/<id>.html as raw HTML block (interactive vtk.js)
PDF output:  embeds state/figures/<id>.png as a standard Markdown image
--]]

local _relay_injected = false

local function fourd_image(args, kwargs)
  local id      = pandoc.utils.stringify(kwargs["id"] or pandoc.Str(""))
  local caption = pandoc.utils.stringify(kwargs["caption"] or pandoc.Str(""))

  if id == "" then
    return pandoc.RawBlock("html",
      '<div style="color:red">⚠ 4d-image: missing required attribute <code>id</code></div>')
  end

  -- ── HTML output: embed self-contained vtk.js widget ───────────────────────
  if quarto.doc.isFormat("html") then
    local fig_path = "state/figures/" .. id .. ".html"
    local f = io.open(fig_path, "r")
    if f then
      local content = f:read("*all")
      f:close()
      -- Embed via srcdoc iframe so the vtk.js canvas is sandboxed in its own
      -- browsing context (window.innerWidth/Height = iframe size, not page viewport).
      local escaped = content:gsub("&", "&amp;"):gsub('"', "&quot;")

      -- Relay script: listens for postMessage from srcdoc iframes and calls
      -- fetch("/camera/...") from the same origin (Quarto page is served by
      -- Panel at the same origin). Only injected once per page.
      local relay_script = ""
      if not _relay_injected then
        _relay_injected = true
        relay_script = [[
<script>
(function(){
  window.addEventListener("message",function(e){
    if(!e.data||e.data.type!=="4dpaper-camera")return;
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
  });
})();
</script>
]]
      end

      return pandoc.RawBlock("html",
        '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
        '<iframe srcdoc="' .. escaped .. '" width="100%" height="600px" ' ..
        'frameborder="0" style="border:none;border-radius:4px;display:block;"></iframe>\n' ..
        (
        caption ~= "" and
            (
            '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' .. caption .. '</figcaption>\n'
            ) or "") ..
        '</figure>\n' ..
        relay_script)
    else
      -- Placeholder shown when figure has not been generated yet
      return pandoc.RawBlock("html",
        '<div style="border:2px dashed #888;padding:1.5rem;text-align:center;' ..
        'border-radius:4px;margin:1rem 0">' ..
        '<strong>⚠ 4D Figure not yet rendered</strong><br>' ..
        'Figure ID: <code>' .. id .. '</code><br>' ..
        '<small>Click <strong>Rebuild HTML</strong> in the dashboard to generate.</small>' ..
        '</div>')
    end

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

return {
  ["4d-image"] = fourd_image,
}
