import os, re

base = r'c:\Users\Acer\Desktop\Code\стартап\startup\html'

template = '''      <nav id="mainNav">
        <a href="main.html" class="nav-link{MAIN}">Главная</a>
        <a href="recording.html" class="nav-link{REC}">Записаться</a>
        <a href="status.html" class="nav-link{STAT}">Статус очереди</a>
        <a href="profile.html" class="nav-link{PROF}">Личный кабинет</a>
        <a href="contacts.html" class="nav-link{CONT}">О проекте &amp; Контакты</a>
      </nav>'''

files = {
    'main.html':      'MAIN',
    'recording.html': 'REC',
    'status.html':    'STAT',
    'profile.html':   'PROF',
    'contacts.html':  'CONT',
    'about.html':     'CONT',
    'auth.html':      '',
}

for fname, active_key in files.items():
    path = os.path.join(base, fname)
    if not os.path.exists(path):
        continue
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    keys = {'MAIN': '', 'REC': '', 'STAT': '', 'PROF': '', 'CONT': ''}
    if active_key:
        keys[active_key] = ' active'
    nav = template
    for k, v in keys.items():
        nav = nav.replace('{' + k + '}', v)
    new_content = re.sub(r'<nav id="mainNav">.*?</nav>', nav, content, flags=re.DOTALL)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f'Fixed: {fname}')

print('Done.')
