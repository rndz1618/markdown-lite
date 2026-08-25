# Toolbar Fix (2026-08-25)

## Root cause
EasyMDE toolbar icons use Font Awesome (`fa fa-bold`, etc.).
After CSP hardening, browsers blocked:
`https://maxcdn.bootstrapcdn.com/font-awesome/latest/css/font-awesome.min.css`

Icons rendered with body font (Inter) → empty glyphs (0×0 px).

## Fix applied in working tree / deploy package
1. Explicit FA 4.7 from jsdelivr in `templates/index.html`
2. `autoDownloadFontAwesome: false` in EasyMDE options
3. CSP allows `https://cdn.jsdelivr.net` and `https://maxcdn.bootstrapcdn.com` for style + font

## Deploy
Copy latest `app.py` + `templates/*` from release package, restart service, hard-refresh browser (Ctrl+Shift+R).
