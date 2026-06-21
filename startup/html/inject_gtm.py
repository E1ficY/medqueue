import glob

gtm_head_snippet = """<!-- Google Tag Manager -->
<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':
new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
})(window,document,'script','dataLayer','GTM-N8QCG64R');</script>
<!-- End Google Tag Manager -->"""

gtm_body_snippet = """<!-- Google Tag Manager (noscript) -->
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-N8QCG64R"
height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
<!-- End Google Tag Manager (noscript) -->"""

# The old GA4 snippet we injected before
old_ga4_snippet = """<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-Y86T417SGF"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-Y86T417SGF');
</script>"""

for f in glob.glob('startup/html/*.html'):
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # 1. Remove the old strict GA4 tag if it's there
    content = content.replace(old_ga4_snippet, '')
    
    # Clean up empty lines from removal if any
    content = content.replace('<head>\n\n', '<head>\n')
    
    # 2. Inject GTM head right after <head>
    if "<!-- Google Tag Manager -->" not in content:
        content = content.replace('<head>', '<head>\n' + gtm_head_snippet, 1)
    
    # 3. Inject GTM body right after body tags (class might vary, so we replace using regex or just look for <body)
    # The body tags look like: <body class="page-auth-avant"> or <body>
    import re
    if "<!-- Google Tag Manager (noscript) -->" not in content:
        content = re.sub(r'(<body[^>]*>)', r'\1\n' + gtm_body_snippet, content, count=1)
        
    with open(f, 'w', encoding='utf-8') as file:
        file.write(content)
        
    print(f"Injected GTM into {f}")
