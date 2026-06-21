import glob

full_ga4_snippet = """<head>
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-Y86T417SGF"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-Y86T417SGF');
</script>"""

old_snippet = """  <!-- Google tag (gtag.js) -->
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
    
    # Remove it from the bottom of head
    content = content.replace(old_snippet, '</head>')
    
    if "<!-- Google tag (gtag.js) -->" not in content:
        content = content.replace('<head>', full_ga4_snippet, 1)
        with open(f, 'w', encoding='utf-8') as file:
            file.write(content)
        print(f"Updated full tag at the VERY TOP of head in {f}")
