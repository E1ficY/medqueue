
with open('startup/html/subscription.html', 'r', encoding='utf-8') as f:
    c = f.read()

# Replace the CSS root vars section (dark -> light)
old_vars = ''':root {
      --bg: #0b1220;
      --bg2: #111827;
      --card: #161f30;
      --card2: #1a2540;
      --border: rgba(255,255,255,.07);
      --accent: #4ade80;
      --accent2: #22c55e;
      --paypal: #003087;
      --paypal2: #009cde;
      --text: #f1f5f9;
      --muted: #64748b;
      --muted2: #94a3b8;
      --plus: #f59e0b;
      --social: #818cf8;
    }'''

new_vars = ''':root {
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
    }'''

# Also fix font
old_font = "family=Manrope:wght@400;500;600;700;800"
new_font = "family=Inter:wght@400;500;600;700;800"

# Fix body
old_body = '''    body {
      font-family: 'Manrope', sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
    }'''

new_body = '''    body {
      font-family: 'Inter', sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
    }'''

# Fix navbar dark bg to light
old_nav = 'background: rgba(11,18,32,.85);'
new_nav = 'background: rgba(255,255,255,.92);'

# Fix toast dark to light
old_toast = '''    #toast {
      position: fixed;
      bottom: 28px; right: 28px;
      background: #1e293b;
      border: 1px solid var(--border);'''
new_toast = '''    #toast {
      position: fixed;
      bottom: 28px; right: 28px;
      background: #ffffff;
      border: 1px solid var(--border);
      box-shadow: 0 4px 20px rgba(0,0,0,.12);'''

# Fix loading dark
old_spinner_border = 'border: 3px solid var(--border);'
new_spinner_border = 'border: 3px solid rgba(0,0,0,.1);'

# Fix error state dark
old_error = '''    .error-state {
      text-align: center;
      padding: 40px 20px;
      background: var(--card);
      border: 1px solid rgba(239,68,68,.2);
      border-radius: 14px;
      color: var(--muted2);
    }'''
new_error = '''    .error-state {
      text-align: center;
      padding: 40px 20px;
      background: var(--card);
      border: 1px solid rgba(239,68,68,.2);
      border-radius: 14px;
      color: var(--muted2);
      box-shadow: var(--shadow);
    }'''

# Plan card shadow
old_plan = '      background: var(--card);\n      border: 1px solid var(--border);\n      border-radius: 18px;'
new_plan = '      background: var(--card);\n      border: 1px solid var(--border);\n      border-radius: 18px;\n      box-shadow: var(--shadow);'

# Status bar shadow
old_status = '      background: var(--card);\n      border: 1px solid var(--border);\n      border-radius: 14px;\n      padding: 16px 24px;\n      margin-bottom: 32px;'
new_status = '      background: var(--card);\n      border: 1px solid var(--border);\n      border-radius: 14px;\n      padding: 16px 24px;\n      margin-bottom: 32px;\n      box-shadow: var(--shadow);'

replacements = [
    (old_vars, new_vars),
    (old_font, new_font),
    (old_body, new_body),
    (old_nav, new_nav),
    (old_toast, new_toast),
    (old_spinner_border, new_spinner_border),
    (old_error, new_error),
    (old_plan, new_plan),
    (old_status, new_status),
]

for old, new in replacements:
    if old in c:
        c = c.replace(old, new)
        print('OK:', old[:40].replace('\n', ' ').strip())
    else:
        print('NOT FOUND:', old[:60].replace('\n', ' ').strip())

with open('startup/html/subscription.html', 'w', encoding='utf-8') as f:
    f.write(c)
print('Done! Lines:', c.count('\n'))
