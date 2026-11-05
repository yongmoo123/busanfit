-- Markdown -> docx: turn raw <br> (used for line breaks inside table cells)
-- into real line breaks. Without this, pandoc drops <br> and cell lines run together.
function RawInline(el)
  if el.format:match('html') and el.text:match('^<br%s*/?>$') then
    return pandoc.LineBreak()
  end
end
