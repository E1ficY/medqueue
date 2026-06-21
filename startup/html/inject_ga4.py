import glob

ga4_snippet = """  <!-- Google tag (gtag.js) -->
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-Y86T417SGF"></script>
</head>"""

for f in glob.glob('startup/html/*.html'):
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    
    if 'G-Y86T417SGF' not in content:
        content = content.replace('</head>', ga4_snippet)
        with open(f, 'w', encoding='utf-8') as file:
            file.write(content)
        print(f"Updated {f}")
