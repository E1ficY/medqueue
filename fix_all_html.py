import os
import re

html_dir = 'startup/html'
files = [f for f in os.listdir(html_dir) if f.endswith('.html')]

light_vars = """:root {
      --bg: #f0f5fb;
      --bg2: #e8eef8;
      --card: #ffffff;
      --card2: #f8fafd;
      --border: rgba(0,0,0,.08);
      --accent: #10b981;
      --accent2: #059669;
      --paypal: #003087;
      --paypal2: #009cde;
      --text: #0f172a;
      --muted: #64748b;
      --muted2: #475569;
      --plus: #d97706;
      --social: #6366f1;
      --shadow: 0 2px 16px rgba(0,0,0,.07);
    }"""

updated = []

for file in files:
    if file == 'subscription.html':
        continue
    filepath = os.path.join(html_dir, file)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Replace root vars
    content = re.sub(r':root\s*\{[^}]+\}', light_vars, content, count=1)
    
    # Replace fonts
    content = content.replace("family=Manrope", "family=Inter")
    content = content.replace("'Manrope'", "'Inter'")
    
    # Fix dark backgrounds and specific styles
    content = re.sub(r'background:\s*rgba\(11,\s*18,\s*32,\s*\.85\);', 'background: rgba(255,255,255,.92);', content)
    content = re.sub(r'background:\s*#1e293b;', 'background: #ffffff;', content)
    content = re.sub(r'border:\s*3px solid var\(--border\);', 'border: 3px solid rgba(0,0,0,.1);', content)
    
    # specific dark colors to var() where it makes sense, or light colors
    content = content.replace('#1e293b', 'var(--card)')
    content = content.replace('#0f172a', 'var(--bg2)')
    content = content.replace('rgba(255,255,255,.1)', 'var(--border)')
    content = content.replace('rgba(255,255,255,0.1)', 'var(--border)')
    content = content.replace('rgba(255, 255, 255, 0.1)', 'var(--border)')
    
    # Add box-shadow to some elements
    # Just a simple hack: find `.card {` or `.panel {` and if no box-shadow, add one (might be tricky)
    
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        updated.append(file)

print(f"Updated {len(updated)} files: {updated}")
