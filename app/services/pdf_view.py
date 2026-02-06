from html import escape


def build_pdf_wrapper_html(token: str, filename: str) -> str:
    title = escape(filename or "file.pdf")
    tok = escape(token)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    html, body {{ height: 100%; margin: 0; background: #0b1220; }}
    .bar {{
      height: 44px; display: flex; align-items: center; gap: 12px;
      padding: 0 12px; box-sizing: border-box;
      color: #e5e7eb; font-family: Arial, sans-serif; font-size: 14px;
      background: #020617; border-bottom: 1px solid rgba(255,255,255,0.08);
    }}
    .bar a {{ color: #93c5fd; text-decoration: none; }}
    .bar a:hover {{ text-decoration: underline; }}
    iframe {{ width: 100%; height: calc(100% - 44px); border: 0; background: #0b1220; }}
  </style>
</head>
<body>
  <div class="bar">
    <div style="flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{title}</div>
    <a href="/pdf/{tok}/download">Download</a>
  </div>
  <iframe src="/pdf/{tok}/raw" title="{title}"></iframe>
</body>
</html>"""
