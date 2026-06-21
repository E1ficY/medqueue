import glob

full_ga4_snippet = """  <!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-Y86T417SGF"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-Y86T417SGF');
</script>
</head>"""

for f in glob.glob('startup/html/*.html'):
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Remove the partial snippet we added before
    partial_snippet = '  <!-- Google tag (gtag.js) -->\n  <script async src="https://www.googletagmanager.com/gtag/js?id=G-Y86T417SGF"></script>\n</head>'
    content = content.replace(partial_snippet, '</head>')
    
    if "gtag('config', 'G-Y86T417SGF');" not in content:
        content = content.replace('</head>', full_ga4_snippet)
        with open(f, 'w', encoding='utf-8') as file:
            file.write(content)
        print(f"Updated full tag in {f}")
