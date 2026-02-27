// MedQueue — Theme toggle
(function () {
  var STORAGE_KEY = 'medqueue_theme';

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    document.querySelectorAll('.theme-checkbox').forEach(function (cb) {
      cb.checked = (theme === 'dark');
    });
  }

  function toggleTheme() {
    var current = document.documentElement.getAttribute('data-theme') || 'light';
    var next = current === 'dark' ? 'light' : 'dark';
    localStorage.setItem(STORAGE_KEY, next);
    applyTheme(next);
  }

  var saved = localStorage.getItem(STORAGE_KEY) || 'light';
  applyTheme(saved);

  window.toggleTheme = toggleTheme;

  document.addEventListener('DOMContentLoaded', function () {
    applyTheme(localStorage.getItem(STORAGE_KEY) || 'light');
  });
})();


// ═══════════════════════════════════════════
//  GTA-style Easter Eggs
//  Codes:  medqueue  |  5462
// ═══════════════════════════════════════════
(function () {

  var SECRETS = {
    'medqueue': {
      label: 'CHEAT ACTIVATED: TERMINAL MODE',
      lines: [
        '> MEDQUEUE OS v1.0  [1986 EDITION]',
        '> Initializing queue management system...',
        '> Loading hospitals database.........OK',
        '> Connecting to clinic network.......OK',
        '> Authenticating user profile........OK',
        '> ',
        '>  ███╗   ███╗███████╗██████╗  ██████╗ ',
        '>  ████╗ ████║██╔════╝██╔══██╗██╔═══██╗',
        '>  ██╔████╔██║█████╗  ██║  ██║██║   ██║',
        '>  ██║╚██╔╝██║██╔══╝  ██║  ██║██║▄▄ ██║',
        '>  ██║ ╚═╝ ██║███████╗██████╔╝╚██████╔╝',
        '>  ╚═╝     ╚═╝╚══════╝╚═════╝  ╚══▀▀═╝ ',
        '> ',
        '>  QUEUE  SYSTEM  READY',
        '> ',
        '> Пасхалка найдена. Уважаем.',
        '> Нажми ESC или кликни чтобы выйти.',
      ]
    },
    '5462': {
      label: 'CHEAT ACTIVATED: КУЛЬТ #5462',
      color: '#a855f7',
      glow: 'rgba(168,85,247,0.5)',
      lines: [
        '> CULT SYSTEM v5462 — ИНИЦИАЛИЗАЦИЯ...',
        '> Проверка лояльности................OK',
        '> Загрузка ритуалов..................OK',
        '> Связь с Самиром....................OK',
        '> ',
        '>   ██████╗ ██╗   ██╗██╗  ████████╗',
        '>  ██╔════╝ ██║   ██║██║  ╚══██╔══╝',
        '>  ██║      ██║   ██║██║     ██║   ',
        '>  ██║      ██║   ██║██║     ██║   ',
        '>  ╚██████╗ ╚██████╔╝███████╗██║   ',
        '>   ╚═════╝  ╚═════╝ ╚══════╝╚═╝   ',
        '> ',
        '>  К У Л Ь Т   # 5 4 6 2',
        '> ',
        '> Добро пожаловать, посвящённый.',
        '> Самир знает о тебе.',
        '> Нажми ESC или кликни чтобы выйти.',
      ]
    }
  };

  var MAX_LEN = Math.max.apply(null, Object.keys(SECRETS).map(function(k){ return k.length; }));
  var buffer = '';
  var bufferTimer = null;
  var BUFFER_TIMEOUT = 1500;

  document.addEventListener('keydown', function (e) {
    var tag = document.activeElement && document.activeElement.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

    buffer += e.key.toLowerCase();
    if (buffer.length > MAX_LEN) buffer = buffer.slice(-MAX_LEN);

    clearTimeout(bufferTimer);
    bufferTimer = setTimeout(function () { buffer = ''; }, BUFFER_TIMEOUT);

    for (var code in SECRETS) {
      if (buffer.slice(-code.length) === code) {
        buffer = '';
        triggerEasterEgg(SECRETS[code]);
        break;
      }
    }
  });

  // ── GTA notification bar ──────────────────
  function showGTABar(label, color, glow, cb) {
    color = color || '#22c55e';
    glow  = glow  || 'rgba(34,197,94,0.4)';

    var bar = document.createElement('div');
    bar.id = 'gtaCheatBar';
    bar.innerHTML = '<span style="opacity:0.55;margin-right:10px;">&#x2713;</span>' + label;
    bar.style.cssText = [
      'position:fixed',
      'top:-60px',
      'left:50%',
      'transform:translateX(-50%)',
      'background:#000',
      'color:' + color,
      'font-family:"Courier New",monospace',
      'font-size:15px',
      'font-weight:700',
      'letter-spacing:0.1em',
      'padding:12px 32px',
      'border-radius:0 0 10px 10px',
      'z-index:999999',
      'border:1px solid ' + color,
      'border-top:none',
      'box-shadow:0 4px 30px ' + glow,
      'transition:top 0.35s cubic-bezier(0.34,1.56,0.64,1)',
      'white-space:nowrap',
    ].join(';');
    document.body.appendChild(bar);

    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        bar.style.top = '0px';
        setTimeout(function () {
          bar.style.top = '-60px';
          setTimeout(function () {
            bar.remove();
            if (cb) cb();
          }, 400);
        }, 1400);
      });
    });
  }

  // ── Terminal overlay ──────────────────────
  function triggerEasterEgg(cfg) {
    if (document.getElementById('terminalOverlay')) return;
    showGTABar(cfg.label, cfg.color, cfg.glow, function () {
      showTerminal(cfg);
    });
  }

  function showTerminal(cfg) {
    var color = cfg.color || '#22c55e';
    var glow  = cfg.glow  || 'rgba(34,197,94,0.7)';

    var overlay = document.createElement('div');
    overlay.id = 'terminalOverlay';
    overlay.style.cssText = [
      'position:fixed', 'inset:0', 'background:#000',
      'z-index:999998', 'display:flex', 'align-items:center',
      'justify-content:center', 'cursor:pointer',
      'animation:termFadeIn 0.4s ease',
    ].join(';');

    var box = document.createElement('pre');
    box.style.cssText = [
      'color:' + color,
      'font-family:"Courier New",monospace',
      'font-size:clamp(11px,1.4vw,15px)',
      'line-height:1.7',
      'text-align:left',
      'max-width:680px',
      'width:90vw',
      'margin:0',
      'white-space:pre-wrap',
      'text-shadow:0 0 8px ' + glow,
    ].join(';');

    var style = document.createElement('style');
    style.textContent =
      '@keyframes termFadeIn{from{opacity:0}to{opacity:1}}' +
      '@keyframes termFadeOut{from{opacity:1}to{opacity:0}}' +
      '#terminalOverlay .cursor{display:inline-block;width:9px;height:1.1em;background:' + color + ';vertical-align:text-bottom;animation:blink 0.8s step-end infinite;}' +
      '@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}';
    document.head.appendChild(style);

    overlay.appendChild(box);
    document.body.appendChild(overlay);

    var LINES = cfg.lines;
    var lineIdx = 0, charIdx = 0, text = '', speed = 18;

    function type() {
      if (lineIdx >= LINES.length) {
        box.innerHTML = text + '<span class="cursor"></span>';
        return;
      }
      var line = LINES[lineIdx];
      if (charIdx < line.length) {
        text += line[charIdx];
        charIdx++;
        box.innerHTML = text + '<span class="cursor"></span>';
        setTimeout(type, charIdx === 1 ? 60 : speed);
      } else {
        text += '\n';
        lineIdx++;
        charIdx = 0;
        box.innerHTML = text + '<span class="cursor"></span>';
        setTimeout(type, lineIdx > 5 ? 30 : 80);
      }
    }
    type();

    function close() {
      overlay.style.animation = 'termFadeOut 0.3s ease forwards';
      setTimeout(function () { overlay.remove(); }, 300);
    }
    overlay.addEventListener('click', close);
    document.addEventListener('keydown', function onEsc(e) {
      if (e.key === 'Escape') { close(); document.removeEventListener('keydown', onEsc); }
    });
    setTimeout(close, 18000);
  }
})();
