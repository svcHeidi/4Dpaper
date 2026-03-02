--[[
4DPaper shortcode handler.

Usage in .qmd:
  {{< 4d-image src="case.foam" field="Vm" id="fig-vm" >}}
  {{< 4d-image src="case.foam" field="activationTime" id="fig-at" time="last" caption="Activation time" >}}

HTML output: embeds state/figures/<id>.html as raw HTML block (interactive vtk.js)
PDF output:  embeds state/figures/<id>.png as a standard Markdown image
--]]

local function fourd_image(args, kwargs)
  local id      = pandoc.utils.stringify(kwargs["id"]      or pandoc.Str(""))
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
      -- Wrap in a figure div for styling
      return pandoc.RawBlock("html",
        '<figure class="fourd-figure">\n' ..
        content .. "\n" ..
        (caption ~= "" and ('<figcaption>' .. caption .. '</figcaption>\n') or "") ..
        '</figure>')
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
      local img = pandoc.Image(caption, fig_path, id)
      return pandoc.Para({img})
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
