import os
import re

html_dir = 'startup/html'
files = [f for f in os.listdir(html_dir) if f.endswith('.html')]
count = 0
for file in files:
    filepath = os.path.join(html_dir, file)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # We want to replace href="../css/styles.css..." with href="../css/styles.css?v=2026-06-11"
    new_content = re.sub(r'styles\.css(\?v=[A-Za-z0-9_\.\-]+)?', 'styles.css?v=2026-06-11-light', content)
    
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        count += 1

print(f"Updated cache busters in {count} HTML files.")
