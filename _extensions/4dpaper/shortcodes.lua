-- 4DPaper shortcode handler
-- Full implementation in Task 4. This stub prevents Quarto errors.

local function fourd_image(args, kwargs)
  local id = pandoc.utils.stringify(kwargs["id"] or pandoc.Str("unknown"))
  return pandoc.RawBlock("html",
    '<div style="border:1px dashed #888;padding:1rem;text-align:center">' ..
    '⚠ 4d-image stub — id: <code>' .. id .. '</code></div>')
end

return {
  ["4d-image"] = fourd_image,
}
