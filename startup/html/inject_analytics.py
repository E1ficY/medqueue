import glob

for f in glob.glob('*.html'):
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    
    if 'analytics.js' not in content:
        content = content.replace('</head>', '  <script src="../js/analytics.js"></script>\n</head>')
        with open(f, 'w', encoding='utf-8') as file:
            file.write(content)
        print(f"Updated {f}")
