// === НАСТРОЙКИ API ===
const DEFAULT_LOCAL_API_ORIGIN = 'https://127.0.0.1:8000';
const isLocal = window.location.protocol === 'file:' || window.location.port === '5500';
const API_BASE = isLocal
  ? DEFAULT_LOCAL_API_ORIGIN
  : window.location.origin;
const API_URL = `${API_BASE}/api`;
const AUTH_STORAGE_KEY = 'medqueue_current_user';

function getAuthHeaders() {
  const user = JSON.parse(localStorage.getItem(AUTH_STORAGE_KEY) || 'null');
  const headers = {
    'Content-Type': 'application/json',
    'ngrok-skip-browser-warning': 'true',
  };
  if (user?.access) headers['Authorization'] = `Bearer ${user.access}`;
  return headers;
}

// Обновляет access-токен через refresh. Возвращает true если успешно.
async function ensureFreshToken() {
  try {
    const user = JSON.parse(localStorage.getItem(AUTH_STORAGE_KEY) || 'null');
    if (!user?.refresh) return false;
    const res = await fetch(`${API_URL}/auth/token/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true' },
      body: JSON.stringify({ refresh: user.refresh })
    });
    if (!res.ok) {
      // refresh тоже истёк — разлогиниваем
      localStorage.removeItem(AUTH_STORAGE_KEY);
      return false;
    }
    const data = await res.json();
    user.access = data.access;
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(user));
    return true;
  } catch { return false; }
}

// Выполняет fetch с авто-обновлением токена при 401
async function authFetch(url, options = {}) {
  // Proactively check if access token is expired before making the request
  const user = getCurrentUser();
  if (user?.access) {
    try {
      const payload = JSON.parse(atob(user.access.split('.')[1]));
      if (payload.exp * 1000 < Date.now()) {
        await ensureFreshToken(); // refresh before request
      }
    } catch { /* can't decode — proceed anyway */ }
  }

  let res = await fetch(url, { ...options, headers: getAuthHeaders() });

  if (res.status === 401) {
    const refreshed = await ensureFreshToken();
    if (refreshed) {
      // Retry with new token
      res = await fetch(url, { ...options, headers: getAuthHeaders() });
    } else {
      // Refresh failed — retry WITHOUT auth header (so AllowAny endpoints still work)
      const anonHeaders = { 'Content-Type': 'application/json' };
      res = await fetch(url, { ...options, headers: anonHeaders });
    }
  }
  return res;
}

// === ДАННЫЕ ===
let hospitals = [];
let myAppointments = [];
let selectedType = 'all'; // Фильтр по типу клиник
let currentHospitalPage = 1;
let currentHospitalFilter = '';
const HOSPITALS_PER_PAGE = 6;
const STATUS_HISTORY_KEY = 'medqueue_status_history';
const DOCTOR_FAVORITES_KEY = 'medqueue_doctor_favorites';
const DOCTOR_COMPARE_KEY = 'medqueue_doctor_compare';
const RECORDING_SCENARIO_KEY = 'medqueue_recording_scenario_v1';
const DEMO_APPOINTMENTS_KEY = 'medqueue_demo_appointments_v1';
const DEMO_REMINDERS_KEY = 'medqueue_demo_reminders_v1';
const DEMO_FLOW_KEY = 'medqueue_demo_flow_v1';
let doctorsFavoritesOnly = false;

// === ЗАЩИТА СТРАНИЦ ПО РОЛИ ===
// Страницы для пациентов (врачи и админы сюда не должны попадать)
const PATIENT_PAGES = ['main.html', 'index.html', 'profile.html', 'recording.html', 'hospital.html', 'subscription.html', 'doctors.html'];
// Страницы только для врача
const DOCTOR_PAGES = ['doctor.html'];
// Страницы только для админа
const ADMIN_PAGES = ['admin-panel.html'];

function enforceRoleAccess() {
  const user = getCurrentUser();
  if (!user) return; // Не авторизован — пусть страница сама обрабатывает

  const path = window.location.pathname;
  const page = path.split('/').pop() || 'main.html';
  const role = user.role || 'patient';

  const isPatientPage = PATIENT_PAGES.some(p => page.includes(p));
  const isDoctorPage  = DOCTOR_PAGES.some(p => page.includes(p));
  const isAdminPage   = ADMIN_PAGES.some(p => page.includes(p));

  // Врач и Adminы не могут заходить на пациентские страницы
  if (isPatientPage && (role === 'doctor' || role === 'admin')) {
    window.location.replace(role === 'admin' ? 'admin-panel.html' : 'doctor.html');
    return;
  }

  // Не-врач не может заходить на страницу врача
  if (isDoctorPage && role !== 'doctor') {
    window.location.replace(role === 'admin' ? 'admin-panel.html' : 'main.html');
    return;
  }

  // Не-админ не может заходить на адмнку
  if (isAdminPage && role !== 'admin') {
    window.location.replace(role === 'doctor' ? 'doctor.html' : 'main.html');
    return;
  }
}

// === ИНИЦИАЛИЗАЦИЯ ===
document.addEventListener('DOMContentLoaded', async function() {
  initGlobalExperienceLayer();
  initSignatureAcrossPages();

  // Защита по роли — выполняется первой
  enforceRoleAccess();

  // Идентификация для аналитики
  if (window.MedQueueAnalytics) {
    const cu = JSON.parse(localStorage.getItem(AUTH_STORAGE_KEY) || 'null');
    if (cu) {
      window.MedQueueAnalytics.identifyUser(cu.id, cu.email, cu.name || cu.first_name, cu.subscription_plan);
    }
  }

  // Очищаем устаревший кэш от предыдущих версий
  // Очищаем устаревшие версии кэша больниц
  localStorage.removeItem('medqueue_hospitals_cache');
  localStorage.removeItem('medqueue_hospitals_cache_v2');
  localStorage.removeItem('medqueue_hospitals_cache_v3');
  localStorage.removeItem('medqueue_hospitals_cache_v4');

  updateAuthNav();

  // Показываем skeleton-загрузку пока грузятся больницы
  const hospList = document.getElementById('hospList');
  if (hospList) {
    hospList.innerHTML = '<p style="grid-column:1/-1;text-align:center;color:var(--muted);padding:40px">⏳ Загружаем клиники...</p>';
  }

  // Запрашиваем разрешение на уведомления
  setTimeout(requestNotificationPermission, 2000);
  
  // Проверяем авторизацию на главной странице
  if (window.location.pathname.includes('main.html') || window.location.pathname.includes('index.html')) {
    checkAuthForMainPage();
  }
  
  await loadHospitals();
  window.hospitals = hospitals; // expose for map
  document.dispatchEvent(new Event('hospitalsReady'));
  syncMainHeroMetrics();
  initSmartFormDrafts();
  initHospitalSelects();
  initMainQuickHospitalPicker();
  renderHospitalCards();
  initSearch();
  initDoctorsCatalogPage();
  initForms();
  initStatusPage();
  highlightActiveNav();
  initPhoneDropdowns();
  initMainWowEffects();
  initInnovationLab();
  initStatusFlowEnhancements();
  initProfileFlowEnhancements();
  initContactsFlowEnhancements();
  initRecordingDemoShowcase();
  processDueReminders();
});

function initGlobalExperienceLayer() {
  initImagePerformanceOptimizations();
  initScrollProgressBar();
  initQuickDock();
  initCommandPalette();
  initCornerThemeToggle();
}

function initImagePerformanceOptimizations() {
  document.querySelectorAll('img').forEach((img) => {
    if (img.closest('.site-header, .topbar, .logo, .mq-brand-badge')) return;
    if (!img.hasAttribute('loading')) img.loading = 'lazy';
    if (!img.hasAttribute('decoding')) img.decoding = 'async';
  });
}

function toggleMobileMenu() {
  const nav = document.getElementById('mainNav');
  if (nav) nav.classList.toggle('mobile-open');
}

function initCornerThemeToggle() {
  if (document.getElementById('mqCornerTheme')) return;

  const btn = document.createElement('button');
  btn.id = 'mqCornerTheme';
  btn.className = 'mq-corner-theme';
  btn.type = 'button';

  const current = document.documentElement.getAttribute('data-theme') || localStorage.getItem('medqueue_theme') || 'light';
  btn.textContent = current === 'dark' ? '☾' : '☀';

  btn.addEventListener('click', () => {
    if (typeof window.toggleTheme === 'function') {
      window.toggleTheme();
    } else {
      const now = document.documentElement.getAttribute('data-theme') || 'light';
      const next = now === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('medqueue_theme', next);
    }
    const after = document.documentElement.getAttribute('data-theme') || localStorage.getItem('medqueue_theme') || 'light';
    btn.textContent = after === 'dark' ? '☾' : '☀';
  });

  document.body.appendChild(btn);
}

function initScrollProgressBar() {
  if (document.getElementById('mqScrollProgress')) return;
  const bar = document.createElement('div');
  bar.id = 'mqScrollProgress';
  document.body.appendChild(bar);

  const update = () => {
    const scrollTop = window.scrollY || document.documentElement.scrollTop;
    const docHeight = document.documentElement.scrollHeight - window.innerHeight;
    const p = docHeight > 0 ? scrollTop / docHeight : 0;
    bar.style.transform = `scaleX(${Math.min(Math.max(p, 0), 1)})`;
  };

  update();
  window.addEventListener('scroll', update, { passive: true });
  window.addEventListener('resize', update);
}

function initQuickDock() {
  if (document.getElementById('mqQuickDock')) return;
  if (document.body.classList.contains('page-doctor-avant') || document.body.classList.contains('page-admin-avant')) return;

  const links = [
    { href: 'main.html', label: 'Главная', icon: '⌂' },
    { href: 'recording.html', label: 'Запись', icon: '✚' },
    { href: 'doctors.html', label: 'Врачи', icon: '⚕' },
    { href: 'profile.html', label: 'Профиль', icon: '◉', isHub: true },
    { href: 'subscription.html', label: 'Плюс', icon: '★' },
    { href: 'contacts%20and%20about.html', label: 'О нас', icon: 'i' },
  ];

  const page = (window.location.pathname.split('/').pop() || '').toLowerCase();
  const dock = document.createElement('aside');
  dock.id = 'mqQuickDock';
  dock.className = 'mq-quick-dock';

  links.forEach((item) => {
    const a = document.createElement('a');
    a.href = item.href;
    a.className = `mq-dock-item${item.isHub ? ' mq-profile-hub' : ''}`;
    if (page === item.href.toLowerCase()) a.classList.add('active');
    a.innerHTML = `<span>${item.icon}</span><small>${item.label}</small>`;
    dock.appendChild(a);
  });

  document.body.appendChild(dock);
}

function initCommandPalette() {
  if (document.getElementById('mqPalette')) return;
  if (document.body.classList.contains('page-doctor-avant') || document.body.classList.contains('page-admin-avant')) return;

  const actions = [
    { title: 'Открыть главную', hint: 'main', action: () => window.location.href = 'main.html' },
    { title: 'Перейти к записи', hint: 'recording', action: () => window.location.href = 'recording.html' },
    { title: 'Проверить очередь', hint: 'status', action: () => window.location.href = 'recording.html#status-check' },
    { title: 'Открыть каталог врачей', hint: 'doctors', action: () => window.location.href = 'doctors.html' },
    { title: 'Личный кабинет', hint: 'profile', action: () => window.location.href = 'profile.html' },
    { title: 'Переключить тему', hint: 'theme', action: () => window.toggleTheme && window.toggleTheme() },
    { title: 'Открыть МедAI', hint: 'ai', action: () => document.getElementById('aiChatBubble')?.click() },
  ];

  const overlay = document.createElement('div');
  overlay.id = 'mqPalette';
  overlay.className = 'mq-palette';
  overlay.innerHTML = `
    <div class="mq-palette-box" role="dialog" aria-label="Командная палитра">
      <div class="mq-palette-head">MedQueue Command</div>
      <input id="mqPaletteInput" type="text" placeholder="Например: запись, очередь, тема" />
      <div id="mqPaletteList" class="mq-palette-list"></div>
      <div class="mq-palette-foot">Ctrl+K открыть · Esc закрыть</div>
    </div>
  `;
  document.body.appendChild(overlay);

  const input = overlay.querySelector('#mqPaletteInput');
  const list = overlay.querySelector('#mqPaletteList');

  let visible = false;

  const close = () => {
    visible = false;
    overlay.classList.remove('open');
  };

  const open = () => {
    visible = true;
    overlay.classList.add('open');
    input.value = '';
    render('');
    setTimeout(() => input.focus(), 20);
  };

  const render = (q) => {
    const term = (q || '').trim().toLowerCase();
    const filtered = actions.filter((a) => !term || a.title.toLowerCase().includes(term) || a.hint.includes(term));
    list.innerHTML = filtered.map((a, i) => `<button class="mq-palette-item" data-idx="${i}"><strong>${a.title}</strong><span>${a.hint}</span></button>`).join('');
    Array.from(list.querySelectorAll('.mq-palette-item')).forEach((btn) => {
      btn.addEventListener('click', () => {
        const idx = Number(btn.getAttribute('data-idx'));
        const action = filtered[idx];
        close();
        action?.action();
      });
    });
  };

  input.addEventListener('input', (e) => render(e.target.value));
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) close();
  });

  document.addEventListener('keydown', (e) => {
    const key = typeof e.key === 'string' ? e.key.toLowerCase() : '';
    if ((e.ctrlKey || e.metaKey) && key === 'k') {
      e.preventDefault();
      visible ? close() : open();
    }
    if (e.key === 'Escape' && visible) close();
  });
}

function initSignatureAcrossPages() {
  const page = (window.location.pathname.split('/').pop() || '').toLowerCase();

  const revealTargets = document.querySelectorAll(
    'main .card, .section-card, .appointment-item, .contact-mini-card, .about-fact, .doctor-card, .plan-item, .content-section, .sidebar-section'
  );

  revealTargets.forEach((el) => {
    if (!el.classList.contains('reveal-up')) {
      el.classList.add('reveal-up');
    }
  });

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('revealed');
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.16 });

  revealTargets.forEach((el, i) => {
    el.style.transitionDelay = `${Math.min(i * 40, 320)}ms`;
    observer.observe(el);
  });

}

function syncMainHeroMetrics() {
  const hospitalsCounter = document.getElementById('mainHospitalsCount');
  if (!hospitalsCounter) return;
  const count = Array.isArray(hospitals) ? hospitals.length : 0;
  hospitalsCounter.setAttribute('data-count-to', String(count));
  hospitalsCounter.textContent = '0';
}

function initMainWowEffects() {
  if (!document.body.classList.contains('page-main-avant')) return;

  const revealItems = document.querySelectorAll('.reveal-up');
  if (revealItems.length) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('revealed');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.18 });

    revealItems.forEach((item, idx) => {
      item.style.transitionDelay = `${Math.min(idx * 55, 420)}ms`;
      observer.observe(item);
    });
  }

  const counters = document.querySelectorAll('[data-count-to]');
  counters.forEach((counter) => {
    const goal = Number(counter.getAttribute('data-count-to')) || 0;
    let value = 0;
    const step = Math.max(1, Math.ceil(goal / 28));

    const timer = setInterval(() => {
      value += step;
      if (value >= goal) {
        value = goal;
        clearInterval(timer);
      }
      counter.textContent = String(value);
    }, 32);
  });
}

// === КАТАЛОГ ВРАЧЕЙ ===
let doctorsCatalog = [];

async function loadDoctorsCatalog({ query = '', specialty = '' } = {}) {
  const params = new URLSearchParams();
  if (query) params.set('q', query);
  if (specialty && specialty !== 'all') params.set('specialty', specialty);

  const url = `${API_URL}/doctors/${params.toString() ? `?${params.toString()}` : ''}`;
  const response = await fetch(url);
  if (!response.ok) throw new Error('Не удалось загрузить врачей');
  const data = await response.json();
  doctorsCatalog = Array.isArray(data) ? data : (data.results || []);
  return doctorsCatalog;
}

function renderDoctorsWowPanel(items) {
  const panel = document.getElementById('doctorsWowPanel');
  if (!panel) return;

  if (!items.length) {
    panel.innerHTML = `
      <div class="doctors-wow-head">Аналитика очереди в реальном времени</div>
      <div class="doctors-wow-grid">
        <article class="doctors-wow-item"><strong>0</strong><span>Нет совпадений по фильтру</span></article>
        <article class="doctors-wow-item"><strong>--</strong><span>Измените поиск или специальность</span></article>
        <article class="doctors-wow-item"><strong>--</strong><span>Прогноз появится автоматически</span></article>
      </div>
    `;
    return;
  }

  const sortedByEta = [...items].sort((a, b) => (a.wait_forecast_minutes || 0) - (b.wait_forecast_minutes || 0));
  const fastest = sortedByEta[0];
  const avgEta = Math.round(items.reduce((sum, d) => sum + Number(d.wait_forecast_minutes || 0), 0) / items.length);
  const avgConfidence = Math.round(items.reduce((sum, d) => sum + Number(d.wait_forecast_confidence || 0), 0) / items.length);

  panel.innerHTML = `
    <div class="doctors-wow-head">Аналитика очереди в реальном времени</div>
    <div class="doctors-wow-grid">
      <article class="doctors-wow-item">
        <strong>${fastest.wait_forecast_minutes || 0} мин</strong>
        <span>Быстрее всего: ${fastest.full_name}</span>
      </article>
      <article class="doctors-wow-item">
        <strong>${avgEta} мин</strong>
        <span>Среднее ожидание по текущему фильтру</span>
      </article>
      <article class="doctors-wow-item">
        <strong>${avgConfidence}%</strong>
        <span>Средняя точность прогноза</span>
      </article>
    </div>
  `;
}

function renderDoctorsCatalogCards(items) {
  const container = document.getElementById('doctorsCatalogList');
  if (!container) return;

  const favorites = getDoctorFavorites();
  const compareIds = getDoctorCompareIds();

  if (!items.length) {
    container.innerHTML = '<p style="grid-column:1/-1;text-align:center;color:var(--muted);padding:24px">Врачи не найдены</p>';
    renderDoctorsComparePanel([]);
    return;
  }

  container.innerHTML = items.map(d => {
    const reviews = Array.isArray(d.latest_reviews) ? d.latest_reviews.slice(0, 1) : [];
    const eta = Number.isFinite(Number(d.wait_forecast_minutes)) ? Number(d.wait_forecast_minutes) : 0;
    const confidence = Number.isFinite(Number(d.wait_forecast_confidence)) ? Number(d.wait_forecast_confidence) : 0;
    const etaText = eta <= 0 ? 'Сейчас без ожидания' : `До приема ~${eta} мин`;
    const confText = confidence > 0 ? `Точность ${confidence}%` : 'Точность уточняется';
    const forecastHint = d.wait_forecast_reason || 'Прогноз формируется по текущей нагрузке и истории приемов.';
    const reviewsHtml = reviews.length
      ? reviews.map(r => {
          const patient = r.patient_name || 'Пациент';
          const rating = Number(r.rating || 0).toFixed(1);
          const text = (r.comment || 'Без комментария').trim().slice(0, 86);
          return `<div style="font-size:11px;color:var(--muted);background:var(--glass);border:1px solid var(--border-soft);padding:6px 8px;border-radius:8px;line-height:1.35">${rating} · ${patient}: ${text}${text.length >= 86 ? '...' : ''}</div>`;
        }).join('')
      : '<div style="font-size:11px;color:var(--muted);background:var(--glass);border:1px solid var(--border-soft);padding:6px 8px;border-radius:8px;line-height:1.35">Пока нет отзывов</div>';
    return `
    <div class="card" style="padding:14px;display:flex;flex-direction:column;gap:7px;border-top:2px solid var(--accent);min-height:320px;height:100%">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;">
        <div style="font-size:15px;font-weight:800;color:var(--text);line-height:1.25">${d.full_name}</div>
        <button type="button" class="mq-doctor-fav" data-doctor-id="${d.id}" style="border:1px solid var(--border-soft);background:${favorites.includes(String(d.id)) ? 'var(--accent-light)' : 'transparent'};color:var(--text-soft);font-size:11px;padding:3px 7px;border-radius:8px;cursor:pointer;white-space:nowrap;">${favorites.includes(String(d.id)) ? '★ В избранном' : '☆ В избранное'}</button>
      </div>
      <div style="font-size:11px;color:var(--accent);font-weight:700;text-transform:uppercase">${d.specialty || 'Специалист'}</div>
      <div style="font-size:12px;color:var(--text-soft)">${d.hospital_name || 'Больница не указана'}</div>
      <div style="display:flex;justify-content:space-between;align-items:center;font-size:12px;color:var(--text-soft)">
        <span>Рейтинг: <strong>${Number(d.avg_rating || 0).toFixed(1)}</strong></span>
        <span>Отзывы: ${d.reviews_count || 0}</span>
      </div>
      <div title="${forecastHint.replace(/"/g, '&quot;')}" style="font-size:11px;color:var(--text);background:rgba(111,156,146,0.12);border:1px solid var(--border-soft);padding:6px 8px;border-radius:8px;line-height:1.35">
        <strong>${etaText}</strong> · ${confText}
      </div>
      ${reviewsHtml}
      <div style="margin-top:auto;display:grid;gap:7px;">
        <button type="button" class="mq-doctor-compare" data-doctor-id="${d.id}" style="font-size:11px;padding:6px 8px;border-radius:8px;border:1px solid var(--border-soft);background:${compareIds.includes(String(d.id)) ? 'rgba(111,156,146,0.18)' : 'transparent'};color:var(--text);cursor:pointer;">${compareIds.includes(String(d.id)) ? 'В сравнении' : 'Добавить в сравнение'}</button>
        <div style="display:flex;justify-content:space-between;align-items:center;font-size:11px;color:var(--muted)">
          <span>Очередь: ${d.current_queue || 0} чел.</span>
          <span>${d.work_hours || ''}</span>
        </div>
        <a class="btn btn-outline" style="font-size:12px;padding:7px 10px" href="recording.html?hospital=${d.hospital_id || ''}&doctor=${d.id}">Записаться</a>
      </div>
    </div>
  `;
  }).join('');

  bindDoctorFavoriteButtons();
  bindDoctorCompareButtons(items);
  renderDoctorsComparePanel(items);
}

function initDoctorsCatalogPage() {
  const listEl = document.getElementById('doctorsCatalogList');
  if (!listEl) return;

  const searchEl = document.getElementById('doctorSearch');
  const specialtyEl = document.getElementById('doctorSpecialtyFilter');
  initDoctorsFlowEnhancements(listEl);

  const apply = async () => {
    listEl.innerHTML = '<p style="grid-column:1/-1;text-align:center;color:var(--muted);padding:24px">⏳ Загружаем врачей...</p>';
    try {
      const items = await loadDoctorsCatalog({
        query: searchEl?.value?.trim() || '',
        specialty: specialtyEl?.value || 'all',
      });
      const filtered = doctorsFavoritesOnly
        ? items.filter((d) => getDoctorFavorites().includes(String(d.id)))
        : items;
      renderDoctorsWowPanel(filtered);
      renderDoctorsCatalogCards(filtered);
      updateDoctorsFlowCounters(items.length, filtered.length);
    } catch (e) {
      renderDoctorsWowPanel([]);
      listEl.innerHTML = '<p style="grid-column:1/-1;text-align:center;color:#dc2626;padding:24px">Ошибка загрузки врачей</p>';
    }
  };

  if (searchEl) searchEl.addEventListener('input', debounce(apply, 250));
  if (specialtyEl) specialtyEl.addEventListener('change', apply);

  apply();
}

function getDoctorFavorites() {
  try {
    const parsed = JSON.parse(localStorage.getItem(DOCTOR_FAVORITES_KEY) || '[]');
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

function setDoctorFavorites(ids) {
  localStorage.setItem(DOCTOR_FAVORITES_KEY, JSON.stringify(ids));
}

function getDoctorCompareIds() {
  try {
    const parsed = JSON.parse(localStorage.getItem(DOCTOR_COMPARE_KEY) || '[]');
    return Array.isArray(parsed) ? parsed.map(String).slice(0, 3) : [];
  } catch {
    return [];
  }
}

function setDoctorCompareIds(ids) {
  const safe = Array.isArray(ids) ? ids.map(String).slice(0, 3) : [];
  localStorage.setItem(DOCTOR_COMPARE_KEY, JSON.stringify(safe));
}

function bindDoctorFavoriteButtons() {
  document.querySelectorAll('.mq-doctor-fav').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = String(btn.getAttribute('data-doctor-id') || '');
      if (!id) return;
      const favorites = getDoctorFavorites();
      const exists = favorites.includes(id);
      const next = exists ? favorites.filter((x) => x !== id) : [...favorites, id];
      setDoctorFavorites(next);
      btn.textContent = exists ? '☆ В избранное' : '★ В избранном';
      btn.style.background = exists ? 'transparent' : 'var(--accent-light)';
      updateDoctorsFlowCounters();
    });
  });
}

function bindDoctorCompareButtons(items) {
  document.querySelectorAll('.mq-doctor-compare').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = String(btn.getAttribute('data-doctor-id') || '');
      if (!id) return;

      const existing = getDoctorCompareIds();
      const has = existing.includes(id);
      let next = existing;

      if (has) {
        next = existing.filter((x) => x !== id);
      } else {
        if (existing.length >= 3) {
          showToast('Можно сравнить максимум 3 врача', 'warning');
          return;
        }
        next = [...existing, id];
      }

      setDoctorCompareIds(next);
      renderDoctorsCatalogCards(items);
    });
  });
}

function renderDoctorsComparePanel(items) {
  const panel = document.getElementById('mqDoctorsComparePanel');
  if (!panel) return;

  const ids = getDoctorCompareIds();
  if (!ids.length) {
    panel.innerHTML = '<div style="font-size:13px;color:var(--muted);">Добавьте до 3 врачей в сравнение, чтобы увидеть ключевые различия.</div>';
    return;
  }

  const lookup = new Map((items || []).map((d) => [String(d.id), d]));
  const selected = ids.map((id) => lookup.get(id)).filter(Boolean);

  if (!selected.length) {
    panel.innerHTML = '<div style="font-size:13px;color:var(--muted);">Выбранные врачи не попали в текущий фильтр. Измените фильтры или пересоберите сравнение.</div>';
    return;
  }

  panel.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px;">
      <div style="font-size:13px;font-weight:700;color:var(--text);">Сравнение врачей</div>
      <button type="button" id="mqDoctorsCompareClear" class="btn btn-outline" style="font-size:11px;padding:6px 10px;">Очистить</button>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:8px;">
      ${selected.map((d) => `
        <article style="border:1px solid var(--border-soft);border-radius:10px;padding:10px;background:var(--card);display:grid;gap:4px;">
          <div style="font-weight:700;color:var(--text);line-height:1.25;">${d.full_name}</div>
          <div style="font-size:12px;color:var(--muted);">${d.specialty}</div>
          <div style="font-size:12px;color:var(--text-soft);">${d.hospital_name}</div>
          <div style="font-size:12px;color:var(--text);">Рейтинг: ${Number(d.avg_rating || 0).toFixed(1)} • Отзывов: ${d.reviews_count || 0}</div>
          <div style="font-size:12px;color:var(--text);">Прогноз ожидания: ${d.wait_forecast_minutes || 0} мин</div>
          <a class="btn btn-outline" style="font-size:11px;padding:6px 10px;margin-top:4px;" href="recording.html?hospital=${d.hospital_id || ''}&doctor=${d.id}">Выбрать</a>
        </article>
      `).join('')}
    </div>
  `;

  const clearBtn = document.getElementById('mqDoctorsCompareClear');
  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      setDoctorCompareIds([]);
      renderDoctorsCatalogCards(items);
    });
  }
}

function initDoctorsFlowEnhancements(listEl) {
  const wrap = listEl.parentElement;
  if (!wrap || wrap.querySelector('#mqDoctorsFlowTools')) return;

  const tools = document.createElement('div');
  tools.id = 'mqDoctorsFlowTools';
  tools.style.cssText = 'display:flex;gap:8px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-top:12px;padding:10px 12px;border:1px solid var(--border-soft);border-radius:10px;background:var(--glass);';
  tools.innerHTML = `
    <div id="mqDoctorsFlowStats" style="font-size:13px;color:var(--text-soft)">Подбор врачей загружается...</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;">
      <button id="mqDoctorsFavToggle" type="button" class="btn btn-outline" style="font-size:12px;padding:8px 12px;">Показать избранных</button>
      <a href="recording.html" class="btn btn-primary" style="font-size:12px;padding:8px 12px;">Быстрая запись</a>
    </div>
  `;

  wrap.insertBefore(tools, listEl);

  const comparePanel = document.createElement('div');
  comparePanel.id = 'mqDoctorsComparePanel';
  comparePanel.style.cssText = 'margin-top:10px;padding:10px 12px;border:1px solid var(--border-soft);border-radius:10px;background:var(--glass);';
  comparePanel.innerHTML = '<div style="font-size:13px;color:var(--muted);">Панель сравнения врачей загружается...</div>';
  wrap.insertBefore(comparePanel, listEl);

  const toggle = document.getElementById('mqDoctorsFavToggle');
  if (toggle) {
    toggle.addEventListener('click', () => {
      doctorsFavoritesOnly = !doctorsFavoritesOnly;
      toggle.textContent = doctorsFavoritesOnly ? 'Показать всех' : 'Показать избранных';
      const specialtyEl = document.getElementById('doctorSpecialtyFilter');
      if (specialtyEl) specialtyEl.dispatchEvent(new Event('change'));
    });
  }
}

function updateDoctorsFlowCounters(total, shown) {
  const stat = document.getElementById('mqDoctorsFlowStats');
  if (!stat) return;
  const fav = getDoctorFavorites().length;
  const totalSafe = typeof total === 'number' ? total : document.querySelectorAll('#doctorsCatalogList .card').length;
  const shownSafe = typeof shown === 'number' ? shown : totalSafe;
  stat.textContent = `Показано: ${shownSafe} из ${totalSafe} • Избранных: ${fav}`;
}

function getCurrentUser() {
  try {
    return JSON.parse(localStorage.getItem(AUTH_STORAGE_KEY) || 'null');
  } catch {
    return null;
  }
}

function isLoggedIn() {
  return Boolean(getCurrentUser());
}

function logout() {
  localStorage.removeItem(AUTH_STORAGE_KEY);
  window.location.href = 'main.html';
}

function updateAuthNav() {
  const nav = document.getElementById('mainNav');
  if (!nav) return;

  const profileLink = nav.querySelector('a[href="profile.html"]');
  const authenticated = isLoggedIn();

  if (profileLink && !authenticated) {
    profileLink.textContent = 'Вход / Регистрация';
    profileLink.setAttribute('href', 'auth.html');
    profileLink.classList.remove('active');
  }

  let logoutLink = nav.querySelector('[data-logout-link]');
  if (authenticated) {
    if (!logoutLink) {
      logoutLink = document.createElement('a');
      logoutLink.href = '#';
      logoutLink.className = 'nav-link';
      logoutLink.textContent = 'Выйти';
      logoutLink.setAttribute('data-logout-link', '1');
      logoutLink.addEventListener('click', function(e) {
        e.preventDefault();
        logout();
      });
      nav.appendChild(logoutLink);
    }
  } else if (logoutLink) {
    logoutLink.remove();
  }
}

// Проверка авторизации для главной
function checkAuthForMainPage() {
  const currentUser = getCurrentUser();
  
  // Если пользователь НЕ авторизован - показываем окно
  if (!currentUser) {
    showAuthPrompt();
  }
}

// Модальное окно авторизации
function showAuthPrompt() {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  const cardBg = isDark ? '#1e2530' : 'white';
  const titleColor = isDark ? '#4ade80' : '#064e3b';
  const textColor = isDark ? '#9ca3af' : '#6b7280';
  const borderColor = isDark ? '#374151' : '#e5e7eb';
  const skipColor = isDark ? '#9ca3af' : '#6b7280';

  const modal = document.createElement('div');
  modal.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.8);
    backdrop-filter: blur(10px);
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: center;
    animation: fadeIn 0.3s ease;
  `;
  
  modal.innerHTML = `
    <div style="
      background: ${cardBg};
      border-radius: 24px;
      padding: 48px;
      max-width: 450px;
      text-align: center;
      box-shadow: 0 30px 80px rgba(0, 0, 0, 0.4);
      animation: slideUp 0.4s ease;
    ">
      <div style="font-size: 64px; margin-bottom: 24px;">🏥</div>
      <h2 style="font-size: 28px; font-weight: 800; margin-bottom: 16px; color: ${titleColor};">
        Добро пожаловать в MedQueue!
      </h2>
      <p style="color: ${textColor}; margin-bottom: 32px; font-size: 16px;">
        Войдите или зарегистрируйтесь, чтобы записаться к врачу и управлять своими визитами
      </p>
      <div style="display: flex; gap: 12px; margin-bottom: 16px;">
        <button onclick="window.location.href='auth.html'" 
                style="flex: 1; padding: 16px; background: linear-gradient(135deg, #0f172a, #6f9c92); color: white; border: none; border-radius: 12px; font-weight: 700; font-size: 16px; cursor: pointer;">
          🚀 Войти / Регистрация
        </button>
      </div>
      <button onclick="this.closest('div').parentElement.remove()" 
              style="padding: 12px 24px; background: transparent; border: 2px solid ${borderColor}; border-radius: 10px; font-weight: 600; color: ${skipColor}; cursor: pointer;">
        Продолжить без входа
      </button>
    </div>
  `;
  
  document.body.appendChild(modal);
  
  const style = document.createElement('style');
  style.textContent = `
    @keyframes fadeIn {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    @keyframes slideUp {
      from { opacity: 0; transform: translateY(30px); }
      to { opacity: 1; transform: translateY(0); }
    }
  `;
  document.head.appendChild(style);
}

// === ЗАГРУЗКА БОЛЬНИЦ ИЗ API (с кэшем) ===
const HOSPITALS_CACHE_KEY = 'medqueue_hospitals_cache_v6'; // v6 — include ratings data
const HOSPITALS_CACHE_TTL = 2 * 60 * 1000; // 2 минуты

async function loadHospitals() {
  // Проверяем кэш перед запросом
  try {
    const cached = JSON.parse(localStorage.getItem(HOSPITALS_CACHE_KEY) || 'null');
    if (cached && (Date.now() - cached.ts) < HOSPITALS_CACHE_TTL) {
      hospitals = cached.data;
      return;
    }
  } catch(e) {}

  try {
    const response = await fetch(`${API_URL}/hospitals/?page_size=100`);
    if (!response.ok) throw new Error('API error ' + response.status);
    const data = await response.json();
    // Обрабатываем оба формата: массив И пагинированный объект {count, results: [...]}
    const items = Array.isArray(data) ? data : (data.results || []);
    hospitals = items.map(h => ({
      id:          h.id,
      name:        h.name,
      type:        h.type,
      address:     h.address,
      phone:       h.phone || '',
      waiting:     h.waiting_time,
      waitingReason: h.waiting_time_reason || '',
      queue:       h.current_queue,
      avgRating:   Number(h.avg_rating || 0),
      reviewsCount: Number(h.reviews_count || 0),
      latitude:    h.latitude,
      longitude:   h.longitude,
    }));
    // Сохраняем в кэш только если реально получили данные
    if (hospitals.length > 0) {
      try {
        localStorage.setItem(HOSPITALS_CACHE_KEY, JSON.stringify({ ts: Date.now(), data: hospitals }));
      } catch(e) {}
    }
  } catch (error) {
    console.error('Ошибка загрузки больниц:', error);
    // Если API не работает, пытаемся взять устаревший кэш
    try {
      const stale = JSON.parse(localStorage.getItem(HOSPITALS_CACHE_KEY) || 'null');
      if (stale) { hospitals = stale.data; return; }
    } catch(e) {}
    hospitals = []; // API недоступен
    // Показываем ошибку в контейнере больниц если он есть
    const container = document.getElementById('hospList');
    if (container) {
      container.innerHTML = '<p style="grid-column:1/-1;text-align:center;color:#dc2626;padding:40px">⚠️ Сервер недоступен. Запустите Django-сервер и обновите страницу.</p>';
    }
  }
}

// === ЗАПОЛНЕНИЕ СЕЛЕКТОВ ===
function initHospitalSelects() {
  const selects = document.querySelectorAll('#hospitalSelect, #hospitalSelectApp, .js-hospital-select');
  
  selects.forEach(select => {
    if (!select) return;
    
    select.innerHTML = '<option value="">Выберите больницу</option>';
    
    hospitals.forEach(h => {
      const opt = document.createElement('option');
      opt.value = h.id;
      opt.textContent = h.name;
      select.appendChild(opt);
    });
  });
}

// === ОТРИСОВКА КАРТОЧЕК БОЛЬНИЦ ===
function renderHospitalCards(filter = '') {
  const container = document.getElementById('hospList');
  if (!container) return;

  currentHospitalFilter = filter;

  const paginationContainer = (() => {
    let el = container.parentElement?.querySelector('.hosp-pagination');
    if (!el && container.parentElement) {
      el = document.createElement('div');
      el.className = 'hosp-pagination';
      container.insertAdjacentElement('afterend', el);
    }
    return el;
  })();

  let filtered = hospitals.filter(h =>
    h.name.toLowerCase().includes(filter.toLowerCase()) ||
    (h.address && h.address.toLowerCase().includes(filter.toLowerCase())) ||
    h.type.toLowerCase().includes(filter.toLowerCase())
  );

  // Фильтр по типу
  if (selectedType !== 'all') {
    filtered = filtered.filter(h => h.type === selectedType);
  }

  if (filtered.length === 0) {
    container.innerHTML = '<p style="grid-column: 1/-1; text-align:center; color:var(--muted)">Ничего не найдено</p>';
    if (paginationContainer) paginationContainer.innerHTML = '';
    return;
  }

  const totalPages = Math.max(1, Math.ceil(filtered.length / HOSPITALS_PER_PAGE));
  if (currentHospitalPage > totalPages) currentHospitalPage = totalPages;
  if (currentHospitalPage < 1) currentHospitalPage = 1;

  const startIndex = (currentHospitalPage - 1) * HOSPITALS_PER_PAGE;
  const pageItems = filtered.slice(startIndex, startIndex + HOSPITALS_PER_PAGE);

  // Буферизация через DocumentFragment — один рефлоу вместо многих
  const TYPE_COLORS = {
    'Поликлиника': '#6f9c92', 'Больница': '#7aa79d',
    'Детская': '#f59e0b',     'Спец. клиника': '#8b5cf6',
  };
  const TYPE_ICONS = {
    'Поликлиника': '🏥', 'Больница': '🏨',
    'Детская': '👶',     'Спец. клиника': '🔬',
  };

  const html = pageItems.map(h => {
    const color  = TYPE_COLORS[h.type] || '#6f9c92';
    const icon   = TYPE_ICONS[h.type]  || '🏥';
    const queueW = Math.min((h.queue || 0) / 20 * 100, 100); // макс. 20 = 100%
    return `
    <div class="card" style="padding:0;overflow:hidden;border-top:3px solid ${color}">
      <div style="padding:20px 20px 16px">
        <div style="display:flex;align-items:flex-start;gap:10px;margin-bottom:10px">
          <div style="width:40px;height:40px;border-radius:10px;background:linear-gradient(135deg,#0f172a,${color});
                      display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0">${icon}</div>
          <div style="flex:1;min-width:0">
            <div class="title" style="margin:0;font-size:14px;line-height:1.3">${h.name}</div>
            <div style="font-size:11px;font-weight:700;color:${color};text-transform:uppercase;letter-spacing:.5px;margin-top:2px">${h.type}</div>
          </div>
        </div>
        <div class="meta" style="font-size:12px;margin-bottom:12px">📍 ${h.address || '—'}</div>

        <!-- Очередь с прогресс-баром -->
        <div style="margin-bottom:4px;display:flex;justify-content:space-between;align-items:center">
          <span style="font-size:12px;color:var(--text-muted)">Очередь</span>
          <span style="font-size:13px;font-weight:800;color:${color}">${h.queue || 0} чел.</span>
        </div>
        <div style="height:4px;background:var(--border-soft);border-radius:4px;margin-bottom:10px;overflow:hidden">
          <div style="height:100%;width:${queueW}%;background:${color};border-radius:4px;transition:width .4s"></div>
        </div>
        <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px">⏱ Ожидание ~${h.waiting} мин</div>
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:12px;color:var(--text-muted)">
          <span>⭐ Рейтинг: <strong style="color:${color}">${(h.avgRating || 0).toFixed(1)}</strong></span>
          <span>🗨️ ${h.reviewsCount || 0} отзывов</span>
        </div>
      </div>

      <!-- Кнопки -->
      <div style="display:flex;border-top:1px solid var(--border-soft)">
        <a class="btn" style="flex:1;padding:11px 0;font-size:13px;text-align:center;border-radius:0;
                              background:transparent;color:var(--accent);font-weight:700;text-decoration:none;
                              border-right:1px solid var(--border-soft)"
           href="hospital.html?id=${h.id}">🏥 Подробнее</a>
        <button class="btn" style="flex:1;padding:11px 0;font-size:13px;border-radius:0;
                                   background:transparent;color:${color};font-weight:700;border:none;cursor:pointer"
                onclick="quickBook(${h.id})">📅 Записаться</button>
      </div>
    </div>
  `}).join('');

  // Одно обновление DOM
  container.innerHTML = html;

  if (paginationContainer) {
    const from = startIndex + 1;
    const to = Math.min(startIndex + HOSPITALS_PER_PAGE, filtered.length);
    const pageButtons = [];

    for (let i = 1; i <= totalPages; i++) {
      const nearCurrent = Math.abs(i - currentHospitalPage) <= 1;
      const edge = i === 1 || i === totalPages;
      if (!nearCurrent && !edge) {
        if (pageButtons[pageButtons.length - 1] !== 'dots') pageButtons.push('dots');
      } else {
        pageButtons.push(i);
      }
    }

    const pagesHtml = pageButtons.map(p => {
      if (p === 'dots') return '<span class="hosp-page-dots">...</span>';
      const active = p === currentHospitalPage ? 'active' : '';
      return `<button class="hosp-page-btn ${active}" onclick="changeHospitalPage(${p})">${p}</button>`;
    }).join('');

    paginationContainer.innerHTML = `
      <div class="hosp-pagination-meta">Показано ${from}-${to} из ${filtered.length} клиник</div>
      <div class="hosp-pagination-controls">
        <button class="hosp-page-btn" ${currentHospitalPage === 1 ? 'disabled' : ''} onclick="changeHospitalPage(${currentHospitalPage - 1})">Назад</button>
        ${pagesHtml}
        <button class="hosp-page-btn" ${currentHospitalPage === totalPages ? 'disabled' : ''} onclick="changeHospitalPage(${currentHospitalPage + 1})">Вперед</button>
      </div>
    `;
  }
}

function changeHospitalPage(page) {
  currentHospitalPage = page;
  renderHospitalCards(currentHospitalFilter);

  const list = document.getElementById('hospList');
  if (list) {
    list.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

// === ФИЛЬТР ПО ТИПУ КЛИНИК ===
function filterByType(type, evt) {
  selectedType = type;
  currentHospitalPage = 1;
  
  // Обновляем активную кнопку
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.classList.remove('active');
  });
  // Поддерживаем оба варианта вызова: filterByType('all', event) и filterByType('all')
  const btn = (evt && evt.target) ? evt.target : (window.event && window.event.target);
  if (btn) btn.classList.add('active');
  
  renderHospitalCards(document.getElementById('search')?.value || '');
}

// === БЫСТРАЯ ЗАПИСЬ ИЗ КАРТОЧКИ ===
function quickBook(hospitalId) {
  if (!isLoggedIn()) {
    showToast('Войдите, чтобы записаться к врачу', 'warning');
    setTimeout(() => {
      window.location.href = 'auth.html?tab=login';
    }, 500);
    return;
  }

  window.location.href = `recording.html?hospital=${hospitalId}`;
}

// === ПОИСК ===
function debounce(fn, delay) {
  let timer;
  return function(...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

function initSearch() {
  const searchInput = document.getElementById('search');
  if (!searchInput) return;

  searchInput.addEventListener('input', debounce((e) => {
    currentHospitalPage = 1;
    renderHospitalCards(e.target.value);
  }, 220));
}

// === ИНИЦИАЛИЗАЦИЯ ФОРМ ===
function initForms() {
  // Мини-форма на главной
  const miniForm = document.getElementById('miniForm');
  if (miniForm) {
    miniForm.addEventListener('submit', handleMiniFormSubmit);
  }
  
  // Полная форма записи
  const appForm = document.getElementById('appointmentForm');
  if (appForm) {
    appForm.addEventListener('submit', handleAppointmentSubmit);
    
    // Автозаполнение ФИО из профиля
    const nameInput = document.getElementById('appName');
    if (nameInput && !nameInput.value) {
      const user = getCurrentUser();
      if (user && user.name) nameInput.value = user.name;
    }

    // Предзаполнение hospital из URL параметров (ПОСЛЕ initHospitalSelects)
    const params = new URLSearchParams(window.location.search);
    const hospitalId = params.get('hospital');
    if (hospitalId) {
      const select = document.getElementById('hospitalSelectApp');
      if (select) {
        select.value = hospitalId;
        // Если опция не нашлась (selects ещё не populated) — попробуем позже
        if (!select.value) {
          setTimeout(() => {
            select.value = hospitalId;
            // после установки — загружаем врачей если функция доступна (recording.html)
            if (select.value && typeof window.loadHospitalDoctors === 'function') {
              window.loadHospitalDoctors(hospitalId);
            }
          }, 500);
        } else {
          // Больница уже выбрана — подгрузим врачей немедленно
          if (typeof window.loadHospitalDoctors === 'function') {
            window.loadHospitalDoctors(hospitalId);
          }
        }
      }
    }

    applyScenarioFromStorageAndQuery();
  }
}

function applyScenarioFromStorageAndQuery() {
  const form = document.getElementById('appointmentForm');
  if (!form) return;

  const params = new URLSearchParams(window.location.search);
  const fromStorage = (() => {
    try { return JSON.parse(localStorage.getItem(RECORDING_SCENARIO_KEY) || 'null'); }
    catch { return null; }
  })();

  const scenario = {
    mode: params.get('mode') || fromStorage?.mode || 'balanced',
    dayPart: params.get('day_part') || fromStorage?.dayPart || 'day',
    priority: Number(params.get('priority') || fromStorage?.priority || 5),
    specialty: params.get('specialty') || fromStorage?.specialty || 'Терапевт',
  };

  const shouldAutoApply = params.get('autoscenario') === '1' || !!fromStorage?.fromMainLab;
  if (!shouldAutoApply) return;

  setTimeout(() => {
    applyRecordingScenario(scenario.mode, scenario);
    try {
      if (fromStorage?.fromMainLab) {
        localStorage.setItem(RECORDING_SCENARIO_KEY, JSON.stringify({ ...fromStorage, fromMainLab: false }));
      }
    } catch {}
  }, 350);
}

// === МИНИ-ФОРМА НА ГЛАВНОЙ ===
async function handleMiniFormSubmit(e) {
  e.preventDefault();

  if (!isLoggedIn()) {
    showToast('Для записи нужен вход в аккаунт', 'warning');
    setTimeout(() => {
      window.location.href = 'auth.html?tab=login';
    }, 500);
    return;
  }
  
  const hospitalId = document.getElementById('hospitalSelect').value;
  const specialty = document.getElementById('specialtySelect').value;
  const datetime = document.getElementById('datetime').value;
  const msgEl = document.getElementById('miniFormMsg');
  
  if (!hospitalId || !datetime) {
    showMessage(msgEl, '❌ Выберите больницу и дату/время', 'error');
    return;
  }
  
  // Отправляем на API
  try {
    const currentUser = JSON.parse(localStorage.getItem(AUTH_STORAGE_KEY) || 'null');
    const response = await authFetch(`${API_URL}/appointments/`, {
      method: 'POST',
      body: JSON.stringify({
        patient_name: currentUser?.name || 'Гость',
        hospital: parseInt(hospitalId),
        specialty: specialty,
        datetime: datetime
      })
    });
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      let msg = 'Ошибка создания записи';
      if (errorData.detail) msg = errorData.detail;
      else { const k = Object.keys(errorData)[0]; if (k) { const v = errorData[k]; msg = Array.isArray(v) ? v[0] : String(v); } }
      throw new Error(msg);
    }
    
    const appointment = await response.json();
    const hospital = hospitals.find(h => h.id === parseInt(hospitalId));
    
    // Уведомление
    notifyAppointmentCreated(appointment, hospital);
    
    // Показываем большое окно с кодом
    msgEl.innerHTML = `
      <div style="margin-top:16px; padding:16px; background:linear-gradient(135deg, #f2f6f4 0%, #e8efec 100%); border-radius:10px; border:2px solid #6f9c92;">
        <div style="text-align:center;">
          <div style="font-size:18px; margin-bottom:8px;">🎉 Вы записаны!</div>
          <div style="font-size:13px; color:#4f776f; margin-bottom:12px;">Сохраните код</div>
          <div style="background:white; padding:12px; border-radius:8px; margin-bottom:12px;">
            <div style="font-size:11px; color:#6b7280; margin-bottom:4px;">КОД ЗАПИСИ</div>
            <div style="font-size:28px; font-weight:900; color:#6f9c92; letter-spacing:3px; font-family:monospace;">
              ${appointment.code}
            </div>
          </div>
          <div style="font-size:12px; margin-bottom:8px;">
            <strong>${hospital.name}</strong><br>
            ${specialty} • ${new Date(datetime).toLocaleDateString('ru-RU')}<br>
            Место в очереди: <strong>${appointment.queue_position}</strong>
          </div>
          <a href="recording.html?code=${appointment.code}#status-check" class="btn btn-primary" style="font-size:12px; padding:6px 12px;">Проверить статус</a>
        </div>
      </div>
    `;
    
    e.target.reset();
    localStorage.removeItem(HOSPITALS_CACHE_KEY); // сбрасываем кэш
    loadHospitals(); // Обновляем очереди
    
  } catch (error) {
    console.error('Ошибка:', error);
    showMessage(msgEl, `❌ ${error.message}`, 'error');
  }
}

// === ПОЛНАЯ ФОРМА ЗАПИСИ ===
async function handleAppointmentSubmit(e) {
  e.preventDefault();

  if (!isLoggedIn()) {
    showToast('Для записи нужен вход в аккаунт', 'warning');
    setTimeout(() => {
      window.location.href = 'auth.html?tab=login';
    }, 500);
    return;
  }
  
  const name       = document.getElementById('appName').value.trim();
  const _phoneCode = document.getElementById('appPhoneCode')?.value || '+7';
  const _phoneNum  = (document.getElementById('appPhone')?.value || '').trim();
  const phone      = _phoneNum ? `${_phoneCode} ${_phoneNum}` : '';
  const hospitalId = document.getElementById('hospitalSelectApp').value;
  const specialty  = document.getElementById('appSpecialty').value;
  const datetime   = document.getElementById('appDatetime').value;
  const comment    = (document.getElementById('appComment')?.value || '').trim();
  const msgEl      = document.getElementById('appMsg');
  
  if (!name || !hospitalId || !datetime) {
    showMessage(msgEl, '❌ Заполните все поля', 'error');
    return;
  }
  if (!specialty) {
    showMessage(msgEl, '❌ Выберите специальность врача', 'error');
    return;
  }
  
  // Отправляем на API
  const doctorId = (() => {
    const el = document.getElementById('appDoctor');
    return el && el.value ? parseInt(el.value) : undefined;
  })();

  const bookingDraft = {
    patient_name: name,
    phone: phone || undefined,
    hospital: parseInt(hospitalId),
    specialty,
    doctor: doctorId,
    datetime,
    comment: comment || undefined,
  };

  try {
    const response = await authFetch(`${API_URL}/appointments/`, {
      method: 'POST',
      body: JSON.stringify(bookingDraft)
    });
    
    if (!response.ok) {
      const errorData = await response.json();
      // Извлекаем первую читаемую ошибку из любого поля
      let msg = 'Ошибка создания записи';
      if (typeof errorData === 'string') {
        msg = errorData;
      } else if (errorData.detail) {
        msg = errorData.detail;
      } else {
        const firstKey = Object.keys(errorData)[0];
        if (firstKey) {
          const val = errorData[firstKey];
          msg = Array.isArray(val) ? val[0] : String(val);
        }
      }
      throw new Error(msg);
    }
    
    const appointment = await response.json();
    const hospital = hospitals.find(h => h.id === parseInt(hospitalId));
    const doctorLine = `<div style="margin-bottom:6px;"><strong>Специальность:</strong> ${specialty}</div>`
      + (appointment.doctor_name
        ? `<div style="margin-bottom:6px;"><strong>Врач:</strong> ${appointment.doctor_name}${appointment.doctor_cabinet ? ' · каб. ' + appointment.doctor_cabinet : ''}</div>`
        : '');
    
    // Показываем большое окно с кодом
    msgEl.innerHTML = `
      <div style="margin-top:16px; padding:20px; background:linear-gradient(135deg, #f2f6f4 0%, #e8efec 100%); border-radius:12px; border:2px solid #6f9c92;">
        <div style="text-align:center; margin-bottom:16px;">
          <div style="font-size:24px; margin-bottom:8px;">🎉 Запись подтверждена!</div>
          <div style="font-size:14px; color:#4f776f; margin-bottom:16px;">Сохраните код для проверки статуса очереди</div>
        </div>
        
        <div style="background:white; padding:16px; border-radius:10px; margin-bottom:16px;">
          <div style="text-align:center;">
            <div style="font-size:13px; color:#6b7280; margin-bottom:8px; font-weight:600;">ВАШ КОД ЗАПИСИ</div>
            <div style="font-size:36px; font-weight:900; color:#6f9c92; letter-spacing:4px; font-family:monospace;">
              ${appointment.code}
            </div>
            <button onclick="copyCode('${appointment.code}')" 
                    class="btn btn-outline" style="margin-top:12px; font-size:13px;">
              📋 Скопировать код
            </button>
          </div>
        </div>
        
        <div style="background:rgba(255,255,255,0.5); padding:12px; border-radius:8px; font-size:13px;">
          <div style="margin-bottom:6px;"><strong>Пациент:</strong> ${name}</div>
          <div style="margin-bottom:6px;"><strong>Больница:</strong> ${hospital.name}</div>
          ${doctorLine}
          <div style="margin-bottom:6px;"><strong>Дата:</strong> ${new Date(datetime).toLocaleString('ru-RU')}</div>
          <div style="margin-bottom:${comment ? '6px' : '0'};"><strong>Место в очереди:</strong> ${appointment.queue_position}</div>
          ${comment ? `<div style="margin-top:2px;padding:8px 10px;background:rgba(0,0,0,0.04);border-radius:6px;border-left:3px solid #6f9c92;"><strong>Комментарий:</strong> ${comment}</div>` : ''}
        </div>
        
        <div style="margin-top:12px; text-align:center;">
          <a href="recording.html?code=${appointment.code}#status-check" class="btn btn-primary">Проверить статус очереди</a>
        </div>
      </div>
    `;
    
    // Sync phone back to user profile
    if (phone) {
      try {
        const u = JSON.parse(localStorage.getItem(AUTH_STORAGE_KEY) || 'null');
        if (u) { u.phone = phone; localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(u)); }
      } catch(e) {}
    }

    e.target.reset();
    localStorage.removeItem(HOSPITALS_CACHE_KEY); // сбрасываем кэш чтобы очередь обновилась
    loadHospitals(); // Обновляем очереди

    scheduleAppointmentReminders(appointment, hospital, { demo: false });
    seedDemoFlowFromAppointment({
      ...appointment,
      hospital_name: hospital?.name || appointment?.hospital_name || 'Клиника',
      specialty,
      patient_name: name,
    });
    
    // Прокрутка к сообщению
    msgEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    
  } catch (error) {
    console.error('Ошибка:', error);
    const networkLike = /failed to fetch|network|load failed|TypeError/i.test(String(error?.message || ''));
    if (!networkLike) {
      showMessage(msgEl, `❌ ${error.message}`, 'error');
      return;
    }

    const demo = createDemoAppointmentFromForm(bookingDraft);
    const hospital = hospitals.find(h => h.id === parseInt(hospitalId)) || { name: 'Демо-клиника' };
    saveDemoAppointment(demo);
    rememberStatusLookup(demo.code, demo);
    renderStatusHistoryPanel();
    scheduleAppointmentReminders(demo, hospital, { demo: true });

    msgEl.innerHTML = `
      <div style="margin-top:16px; padding:20px; background:linear-gradient(135deg,#fff7ed 0%,#fef3c7 100%); border-radius:12px; border:2px solid #f59e0b;">
        <div style="text-align:center; margin-bottom:12px;">
          <div style="font-size:22px; margin-bottom:8px;">🧪 Демо-запись создана</div>
          <div style="font-size:13px;color:#92400e;">Сервер недоступен, поэтому включен офлайн-режим для презентации.</div>
        </div>
        <div style="background:white; padding:14px; border-radius:10px; margin-bottom:12px; text-align:center;">
          <div style="font-size:12px;color:#6b7280; margin-bottom:5px;">КОД ДЕМО-ЗАПИСИ</div>
          <div style="font-size:34px; font-weight:900; color:#b45309; letter-spacing:4px; font-family:monospace;">${demo.code}</div>
        </div>
        <div style="font-size:13px;color:#78350f;background:rgba(255,255,255,.56);padding:10px;border-radius:8px;">
          ${hospital.name} • ${specialty} • очередь ${demo.queue_position} • ожидание ~${demo.estimated_wait_time} мин
        </div>
        <div style="margin-top:12px; text-align:center;">
          <a href="recording.html?code=${demo.code}#status-check" class="btn btn-primary">Проверить статус и показать игру</a>
        </div>
      </div>
    `;
    showToast('Сработал офлайн-демо режим записи', 'warning');
  }
}

// === ПРОВЕРКА СТАТУСА ===
function initStatusPage() {
  const checkForm = document.getElementById('checkForm');
  if (!checkForm) return;
  renderStatusHistoryPanel();
  
  // Проверяем URL параметры (если перешли из личного кабинета)
  const params = new URLSearchParams(window.location.search);
  const codeFromUrl = params.get('code');
  
  checkForm.addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const code = document.getElementById('code').value.trim().toUpperCase();
    const resultDiv = document.getElementById('result');
    
    if (!code) {
      resultDiv.style.display = 'block';
      resultDiv.innerHTML = '<div style="padding:12px; background:#fee2e2; border-radius:8px; color:#dc2626;">❌ Введите код записи</div>';
      return;
    }
    
    try {
      const response = await fetch(`${API_URL}/appointments/check/${code}/`);
      
      if (!response.ok) {
        throw new Error('Запись не найдена');
      }
      
      const appointment = await response.json();
      rememberStatusLookup(code, appointment);
      renderStatusHistoryPanel();
      seedDemoFlowFromAppointment({
        ...appointment,
        created_at: Date.now(),
      });
      const datetime = new Date(appointment.datetime);
      const waitTime = appointment.estimated_wait_time;
      
      resultDiv.style.display = 'block';
      resultDiv.innerHTML = `
        <div style="padding:20px; background:linear-gradient(135deg, #e8efec 0%, #bfdbfe 100%); border-radius:12px; border:2px solid #7aa79d;">
          <div style="display:flex; align-items:center; gap:12px; margin-bottom:16px;">
            <div style="width:48px; height:48px; background:linear-gradient(135deg,#0f172a,#6f9c92); border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:24px;">
              ✓
            </div>
            <div>
              <div style="font-weight:800; font-size:18px; color:#064e3b;">Запись подтверждена</div>
              <div style="color:#166534; font-size:14px; margin-top:2px;">Код: ${appointment.code}</div>
            </div>
          </div>
          
          <div style="background:white; padding:16px; border-radius:10px; margin-bottom:12px;">
            <div style="display:grid; gap:12px;">
              <div>
                <div style="font-size:12px; color:#6b7280; margin-bottom:4px;">ПАЦИЕНТ</div>
                <div style="font-weight:700; font-size:16px; color:#111827;">${appointment.patient_name}</div>
              </div>
              
              <div style="border-top:1px solid #e5e7eb; padding-top:12px;">
                <div style="font-size:12px; color:#6b7280; margin-bottom:4px;">БОЛЬНИЦА</div>
                <div style="font-weight:600; color:#111827;">${appointment.hospital_name}</div>
                <div style="font-size:13px; color:#6b7280; margin-top:2px;">📍 ${appointment.hospital_address}</div>
              </div>
              
              <div style="border-top:1px solid #e5e7eb; padding-top:12px;">
                <div style="font-size:12px; color:#6b7280; margin-bottom:4px;">СПЕЦИАЛИСТ</div>
                <div style="font-weight:600; color:#111827;">${appointment.specialty}</div>
                ${appointment.doctor_name ? `<div style="font-size:13px; color:#374151; margin-top:4px;">👨‍⚕️ ${appointment.doctor_name}${appointment.doctor_cabinet ? ' · каб. ' + appointment.doctor_cabinet : ''}</div>` : ''}
              </div>
              
              <div style="border-top:1px solid #e5e7eb; padding-top:12px;">
                <div style="font-size:12px; color:#6b7280; margin-bottom:4px;">ДАТА И ВРЕМЯ</div>
                <div style="font-weight:600; color:#111827;">
                  🕐 ${datetime.toLocaleDateString('ru-RU')} в ${datetime.toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit'})}
                </div>
              </div>
              ${appointment.comment ? `
              <div style="border-top:1px solid #e5e7eb; padding-top:12px;">
                <div style="font-size:12px; color:#6b7280; margin-bottom:4px;">КОММЕНТАРИЙ К ЗАПИСИ</div>
                <div style="font-size:14px; color:#111827; background:#f2f6f4; padding:10px 12px; border-radius:8px; border-left:3px solid #6f9c92;">${appointment.comment}</div>
              </div>` : ''}
              ${appointment.doctor_recommendation ? `
              <div style="border-top:1px solid #e5e7eb; padding-top:12px;">
                <div style="font-size:12px; color:#6b7280; margin-bottom:4px;">ЗАКЛЮЧЕНИЕ ПРИЕМА</div>
                <div style="font-size:14px; color:#1f2937; background:#f2f6f4; padding:10px 12px; border-radius:8px; border-left:3px solid #7aa79d;">${appointment.doctor_recommendation}</div>
              </div>` : ''}
              ${appointment.prescribed_medications ? `
              <div style="border-top:1px solid #e5e7eb; padding-top:12px;">
                <div style="font-size:12px; color:#6b7280; margin-bottom:4px;">РЕЦЕПТ</div>
                <div style="font-size:14px; color:#1f2937; background:#eef9f6; padding:10px 12px; border-radius:8px; border-left:3px solid #5c887f; white-space:pre-wrap;">${appointment.prescribed_medications}</div>
                ${appointment.prescription_confirmed ? `<div style="font-size:12px;color:#4f776f;margin-top:6px;">Подтверждено врачом: ${appointment.prescription_confirmed_by || 'врач'}${appointment.prescription_confirmed_at ? ' • ' + new Date(appointment.prescription_confirmed_at).toLocaleString('ru-RU') : ''}</div>` : ''}
              </div>` : ''}
            </div>
          </div>
          
          <div style="background:#f2f6f4; padding:16px; border-radius:10px; border:1px solid #5eead4; margin-bottom:12px;">
            <div style="text-align:center;">
              <div style="font-size:13px; color:#4f776f; margin-bottom:6px; font-weight:600;">ВАШЕ МЕСТО В ОЧЕРЕДИ</div>
              <div style="font-size:42px; font-weight:900; color:#5c887f; line-height:1;">${appointment.queue_position}</div>
              <div style="font-size:14px; color:#166534; margin-top:8px;">
                ⏱️ Примерное ожидание: <strong>~${waitTime} мин</strong>
              </div>
            </div>
          </div>
          
          <div style="background:#fffbea; padding:12px; border-radius:8px; border:1px solid #fde68a; margin-bottom:12px;">
            <div style="font-size:13px; color:#92400e;">
              💡 <strong>Совет:</strong> Приходите за 10 минут до приёма. Мы пришлём SMS, когда подойдёт ваша очередь.
            </div>
          </div>

          ${(appointment.care_plus_support_available || appointment.auto_taxi_available) ? `
          <div style="background:#f2f6f4; padding:12px; border-radius:8px; border:1px solid #a5f3fc; margin-bottom:12px;">
            <div style="font-size:13px; color:#155e75;">
              ✨ <strong>Care Plus:</strong> доступен персональный план после приёма и гибкое приоритетное перепланирование.
            </div>
          </div>` : ''}
          
          <button class="btn btn-outline" style="width:100%;" onclick="cancelAppointment('${appointment.code}')">
            Отменить запись
          </button>
        </div>
      `;

      renderQueueCompanion(appointment);
      
    } catch (error) {
      console.error('Ошибка:', error);

      const demo = getDemoAppointmentByCode(code);
      if (demo) {
        const live = computeLiveDemoQueue(demo);
        rememberStatusLookup(code, live);
        renderStatusHistoryPanel();
        seedDemoFlowFromAppointment({ ...live, created_at: live.created_at || Date.now() });
        resultDiv.style.display = 'block';
        resultDiv.innerHTML = `
          <div style="padding:18px; background:linear-gradient(135deg,#ecfccb 0%,#d9f99d 100%); border-radius:12px; border:2px solid #65a30d;">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;">
              <div>
                <div style="font-weight:900;color:#365314;font-size:18px;">✅ Демо-статус найден</div>
                <div style="font-size:13px;color:#4d7c0f;">Код: ${live.code} • офлайн-поток для показа функционала</div>
              </div>
              <span style="padding:5px 10px;border-radius:999px;background:#365314;color:#fff;font-size:12px;font-weight:700;">DEMO MODE</span>
            </div>
            <div style="margin-top:12px;background:#fff;padding:12px;border-radius:10px;display:grid;gap:8px;">
              <div><strong>Пациент:</strong> ${live.patient_name}</div>
              <div><strong>Клиника:</strong> ${live.hospital_name}</div>
              <div><strong>Специалист:</strong> ${live.specialty}</div>
              <div><strong>Место в очереди:</strong> ${live.queue_position}</div>
              <div><strong>Примерное ожидание:</strong> ~${live.estimated_wait_time} мин</div>
              <div style="font-size:12px;color:#4b5563;">Обновляйте проверку кнопкой «Обновить последний код» чтобы видеть изменение ожидания.</div>
            </div>
          </div>
        `;
        renderQueueCompanion(live);
        return;
      }

      resultDiv.style.display = 'block';
      resultDiv.innerHTML = `
        <div style="padding:16px; background:#fef3c7; border-radius:10px; border:1px solid #fde68a; color:#92400e;">
          <p style="margin:0; font-weight:700; margin-bottom:8px;">⚠️ Запись не найдена</p>
          <p style="margin:0; font-size:14px;">Код: <strong>${code}</strong></p>
          <p style="margin:12px 0 0; font-size:13px; opacity:0.8;">
            Возможно, вы ввели неверный код или запись была отменена.
          </p>
        </div>
      `;
    }
  });

  if (codeFromUrl) {
    const codeInput = document.getElementById('code');
    if (codeInput) {
      codeInput.value = codeFromUrl;
      checkForm.dispatchEvent(new Event('submit'));
    }
  }
}

function getStatusHistory() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STATUS_HISTORY_KEY) || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function rememberStatusLookup(code, appointment) {
  const entry = {
    code,
    hospital_name: appointment?.hospital_name || 'Клиника',
    queue_position: appointment?.queue_position ?? '-',
    checked_at: Date.now(),
  };
  const history = getStatusHistory().filter((x) => x.code !== code);
  history.unshift(entry);
  localStorage.setItem(STATUS_HISTORY_KEY, JSON.stringify(history.slice(0, 6)));
}

function renderStatusHistoryPanel() {
  const form = document.getElementById('checkForm');
  if (!form) return;

  let box = document.getElementById('mqStatusHistory');
  if (!box) {
    box = document.createElement('div');
    box.id = 'mqStatusHistory';
    box.style.cssText = 'margin-top:12px;padding:12px;border:1px solid var(--border-soft);border-radius:10px;background:var(--glass);';
    form.appendChild(box);
  }

  const history = getStatusHistory();
  if (!history.length) {
    box.innerHTML = '<div style="font-size:13px;color:var(--muted)">История проверок появится после первого запроса.</div>';
    return;
  }

  box.innerHTML = `
    <div style="font-size:13px;color:var(--text-soft);margin-bottom:8px;font-weight:700;">Последние проверки</div>
    <div style="display:grid;gap:6px;">
      ${history.map((h) => `
        <button type="button" class="mq-status-history-item" data-code="${h.code}" style="text-align:left;border:1px solid var(--border-soft);background:var(--card);padding:8px 10px;border-radius:8px;cursor:pointer;">
          <strong>${h.code}</strong> · ${h.hospital_name} · очередь ${h.queue_position}
        </button>
      `).join('')}
    </div>
  `;

  box.querySelectorAll('.mq-status-history-item').forEach((btn) => {
    btn.addEventListener('click', () => {
      const codeInput = document.getElementById('code');
      const formEl = document.getElementById('checkForm');
      if (!codeInput || !formEl) return;
      codeInput.value = btn.getAttribute('data-code') || '';
      formEl.dispatchEvent(new Event('submit'));
    });
  });
}

function initRecordingFlowEnhancements() {
  const form = document.getElementById('appointmentForm');
  if (!form || document.getElementById('mqRecordingFlow')) return;

  const panel = document.createElement('div');
  panel.id = 'mqRecordingFlow';
  panel.className = 'card';
  panel.style.cssText = 'margin-bottom:14px;padding:14px;border:1px solid var(--border-soft);background:var(--glass);';
  panel.innerHTML = `
    <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap;">
      <div>
        <div style="font-weight:800;color:var(--text);">Умный сценарий записи</div>
        <div id="mqRecHint" style="font-size:13px;color:var(--muted);">Настройте сценарий, примените, проверьте и подтвердите запись.</div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;flex:1;min-width:240px;">
        <select id="mqRecMode" style="padding:8px 10px;border:1px solid var(--border-soft);border-radius:8px;background:var(--card);color:var(--text);">
          <option value="fast">Самый быстрый</option>
          <option value="balanced" selected>Сбалансированный</option>
          <option value="next">Ближайшее окно</option>
        </select>
        <select id="mqRecDayPart" style="padding:8px 10px;border:1px solid var(--border-soft);border-radius:8px;background:var(--card);color:var(--text);">
          <option value="morning">Утро</option>
          <option value="day" selected>День</option>
          <option value="evening">Вечер</option>
        </select>
        <select id="mqRecSpecialty" style="padding:8px 10px;border:1px solid var(--border-soft);border-radius:8px;background:var(--card);color:var(--text);">
          <option value="Терапевт">Терапевт</option>
          <option value="Кардиолог">Кардиолог</option>
          <option value="Невролог">Невролог</option>
          <option value="Педиатр">Педиатр</option>
          <option value="Стоматолог">Стоматолог</option>
          <option value="Хирург">Хирург</option>
        </select>
        <input id="mqRecPriority" type="range" min="1" max="10" value="6" />
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <button type="button" id="mqRecApply" class="btn btn-outline" style="font-size:12px;padding:8px 12px;">Применить сценарий</button>
        <button type="button" id="mqRecReview" class="btn btn-primary" style="font-size:12px;padding:8px 12px;">К подтверждению</button>
      </div>
    </div>
  `;

  form.parentElement.insertBefore(panel, form);

  const applyBtn = panel.querySelector('#mqRecApply');
  if (applyBtn) {
    applyBtn.addEventListener('click', () => {
      const mode = panel.querySelector('#mqRecMode')?.value || 'balanced';
      const dayPart = panel.querySelector('#mqRecDayPart')?.value || 'day';
      const specialty = panel.querySelector('#mqRecSpecialty')?.value || 'Терапевт';
      const priority = Number(panel.querySelector('#mqRecPriority')?.value || 6);
      applyRecordingScenario(mode, { dayPart, specialty, priority });
    });
  }

  const reviewBtn = panel.querySelector('#mqRecReview');
  if (reviewBtn) {
    reviewBtn.addEventListener('click', () => {
      const submitBtn = form.querySelector('button[type="submit"]');
      if (submitBtn) submitBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  }
}

function applyRecordingScenario(mode, options = {}) {
  const select = document.getElementById('hospitalSelectApp');
  const dtInput = document.getElementById('appDatetime');
  const dtLabel = document.getElementById('dtSelectedLabel');
  const hint = document.getElementById('mqRecHint');
  const specInput = document.getElementById('appSpecialty');
  const noteInput = document.getElementById('appComment');
  if (!select || !dtInput) return;

  if (!Array.isArray(hospitals) || !hospitals.length) {
    if (hint) hint.textContent = 'Сначала дождитесь загрузки списка клиник.';
    return;
  }

  const dayPart = options.dayPart || 'day';
  const specialty = options.specialty || 'Терапевт';
  const priority = Math.max(1, Math.min(10, Number(options.priority || 5)));

  const sorted = [...hospitals].sort((a, b) => {
    const queueA = Number(a.queue || 0);
    const queueB = Number(b.queue || 0);
    const ratingA = Number(a.avgRating || 0);
    const ratingB = Number(b.avgRating || 0);
    if (mode === 'fast') return queueA - queueB;
    if (mode === 'next') return (queueA * 2 - ratingA) - (queueB * 2 - ratingB);
    return (queueA - ratingA * 0.9) - (queueB - ratingB * 0.9);
  });

  const pick = sorted[0];
  if (!pick) return;

  select.value = String(pick.id);
  select.dispatchEvent(new Event('change'));

  const now = new Date();
  const target = new Date(now);
  if (mode === 'next' || priority >= 8) {
    target.setHours(now.getHours() + 2 + (priority >= 9 ? 0 : 1));
    target.setMinutes(0, 0, 0);
  } else {
    target.setDate(target.getDate() + 1);
    const byPart = { morning: 9, day: 13, evening: 18 };
    target.setHours(byPart[dayPart] || 13, 0, 0, 0);
  }

  const pad = (n) => String(n).padStart(2, '0');
  const iso = `${target.getFullYear()}-${pad(target.getMonth() + 1)}-${pad(target.getDate())}T${pad(target.getHours())}:${pad(target.getMinutes())}`;
  dtInput.value = iso;
  if (dtLabel) {
    dtLabel.textContent = `Выбрано: ${target.toLocaleDateString('ru-RU')} ${target.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}`;
  }

  if (specInput) {
    specInput.value = specialty;
    const chip = document.querySelector(`#specGrid .spec-chip[data-value="${specialty}"]`);
    if (chip) chip.click();
  }

  if (noteInput && !noteInput.value) {
    noteInput.value = `Сценарий: ${mode}, приоритет ${priority}/10, окно: ${dayPart === 'morning' ? 'утро' : dayPart === 'evening' ? 'вечер' : 'день'}.`;
  }

  if (typeof window.loadHospitalDoctors === 'function') {
    window.loadHospitalDoctors(String(pick.id));
  }

  if (hint) {
    hint.textContent = `Сценарий применен: ${pick.name} • ${specialty} • очередь ${pick.queue || 0} чел.`;
  }
}

function initStatusFlowEnhancements() {
  const checkForm = document.getElementById('checkForm');
  if (!checkForm || document.getElementById('mqStatusFlowTools')) return;

  const tools = document.createElement('div');
  tools.id = 'mqStatusFlowTools';
  tools.style.cssText = 'display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:12px;';
  tools.innerHTML = `
    <button type="button" id="mqStatusRefresh" class="btn btn-outline" style="font-size:12px;padding:8px 12px;">Обновить последний код</button>
    <button type="button" id="mqStatusClearHistory" class="btn btn-outline" style="font-size:12px;padding:8px 12px;">Очистить историю</button>
  `;

  checkForm.appendChild(tools);

  const refreshBtn = document.getElementById('mqStatusRefresh');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => {
      const history = getStatusHistory();
      const last = history[0];
      if (!last) {
        showToast('История проверок пока пуста', 'info');
        return;
      }
      const codeInput = document.getElementById('code');
      if (!codeInput) return;
      codeInput.value = last.code;
      checkForm.dispatchEvent(new Event('submit'));
    });
  }

  const clearBtn = document.getElementById('mqStatusClearHistory');
  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      localStorage.removeItem(STATUS_HISTORY_KEY);
      renderStatusHistoryPanel();
      showToast('История проверок очищена', 'success');
    });
  }
}

function initProfileFlowEnhancements() {
  if (!document.body.classList.contains('page-profile-avant')) return;
  const list = document.getElementById('appointmentsList');
  if (!list || document.getElementById('mqProfileTools')) return;

  const tools = document.createElement('div');
  tools.id = 'mqProfileTools';
  tools.style.cssText = 'display:flex;gap:8px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin:10px 0 12px;padding:10px;border:1px solid var(--border-soft);border-radius:10px;background:var(--glass);';
  tools.innerHTML = `
    <input id="mqProfileSearch" type="text" placeholder="Фильтр записей по клинике, коду, врачу..." style="flex:1;min-width:240px;padding:9px 10px;border:1px solid var(--border-soft);border-radius:8px;background:var(--card);color:var(--text);" />
    <button id="mqProfileCopyCodes" type="button" class="btn btn-outline" style="font-size:12px;padding:8px 12px;">Скопировать коды</button>
  `;

  list.parentElement.insertBefore(tools, list);

  const search = document.getElementById('mqProfileSearch');
  if (search) {
    search.addEventListener('input', () => {
      const q = (search.value || '').trim().toLowerCase();
      const cards = Array.from(list.children);
      cards.forEach((card) => {
        const txt = (card.textContent || '').toLowerCase();
        card.style.display = !q || txt.includes(q) ? '' : 'none';
      });
    });
  }

  const copyBtn = document.getElementById('mqProfileCopyCodes');
  if (copyBtn) {
    copyBtn.addEventListener('click', async () => {
      const text = list.textContent || '';
      const codes = Array.from(new Set((text.match(/[A-Z0-9]{5,10}/g) || []).filter((x) => /\d/.test(x))));
      if (!codes.length) {
        showToast('Коды записей не найдены', 'info');
        return;
      }
      try {
        await navigator.clipboard.writeText(codes.join('\n'));
        showToast(`Скопировано кодов: ${codes.length}`, 'success');
      } catch {
        showToast('Не удалось скопировать коды', 'error');
      }
    });
  }
}

function initContactsFlowEnhancements() {
  if (!document.body.classList.contains('page-contacts-avant')) return;
  const section = document.getElementById('contacts');
  if (!section || document.getElementById('mqContactsTools')) return;

  const cards = Array.from(section.querySelectorAll('.contact-mini-card'));
  if (!cards.length) return;

  const tools = document.createElement('div');
  tools.id = 'mqContactsTools';
  tools.style.cssText = 'display:flex;gap:8px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin:10px 0 14px;padding:10px;border:1px solid var(--border-soft);border-radius:10px;background:var(--glass);';
  tools.innerHTML = `
    <input id="mqContactsSearch" type="text" placeholder="Поиск по имени, роли, описанию..." style="flex:1;min-width:240px;padding:9px 10px;border:1px solid var(--border-soft);border-radius:8px;background:var(--card);color:var(--text);" />
    <div id="mqContactsCount" style="font-size:13px;color:var(--text-soft)"></div>
  `;
  section.insertBefore(tools, section.querySelector('.contact-mini-grid'));

  const count = document.getElementById('mqContactsCount');
  const refreshCount = () => {
    const shown = cards.filter((c) => c.style.display !== 'none').length;
    if (count) count.textContent = `Показано: ${shown}/${cards.length}`;
  };

  const search = document.getElementById('mqContactsSearch');
  if (search) {
    search.addEventListener('input', () => {
      const q = (search.value || '').trim().toLowerCase();
      cards.forEach((card) => {
        const txt = (card.textContent || '').toLowerCase();
        card.style.display = !q || txt.includes(q) ? '' : 'none';
      });
      refreshCount();
    });
  }

  refreshCount();
}

// === ОТМЕНА ЗАПИСИ ===
async function cancelAppointment(code) {
  if (!confirm('Вы уверены, что хотите отменить запись?')) {
    return;
  }
  
  try {
    const response = await fetch(`${API_URL}/appointments/cancel/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ code: code })
    });
    
    if (!response.ok) throw new Error('Ошибка отмены записи');
    
    const resultDiv = document.getElementById('result');
    if (resultDiv) {
      resultDiv.style.display = 'block';
      resultDiv.innerHTML = `
        <div style="padding:16px; background:#dcfce7; border-radius:10px; border:1px solid #b8cbc6; color:#166534;">
          <p style="margin:0; font-weight:700; margin-bottom:8px;">✅ Запись отменена</p>
          <p style="margin:0; font-size:14px;">Код <strong>${code}</strong> больше не активен.</p>
        </div>
      `;
    }
    
    alert('✅ Запись успешно отменена');
    localStorage.removeItem(HOSPITALS_CACHE_KEY); // сбрасываем кэш
    loadHospitals(); // Обновляем очереди
    
  } catch (error) {
    console.error('Ошибка:', error);
    alert('❌ Ошибка отмены записи');
  }
}

// === ПОДСВЕТКА АКТИВНОЙ ССЫЛКИ ===
function highlightActiveNav() {
  document.querySelectorAll('nav .nav-link').forEach(a => {
    try {
      const href = new URL(a.href, location.href);
      const current = location.pathname.split('/').pop() || 'index.html';
      const target = href.pathname.split('/').pop() || 'index.html';
      if (current === target) a.classList.add('active');
    } catch(e) {}
  });
}

// === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
function showMessage(element, text, type = 'info') {
  if (!element) return;
  
  element.textContent = text;
  element.style.color = type === 'error' ? '#dc2626' : type === 'success' ? '#6f9c92' : '#6b7280';
  element.style.fontWeight = '600';
  
  setTimeout(() => {
    element.textContent = '';
  }, 5000);
}

// === КОПИРОВАНИЕ КОДА С УВЕДОМЛЕНИЕМ ===
function copyCode(code) {
  navigator.clipboard.writeText(code).then(() => {
    showToast('✅ Код скопирован!');
  }).catch(() => {
    showToast('❌ Не удалось скопировать', 'error');
  });
}

// === КРАСИВОЕ УВЕДОМЛЕНИЕ (TOAST) ===
function showToast(message, type = 'success') {
  // Удаляем старое уведомление если есть
  const oldToast = document.getElementById('toast-notification');
  if (oldToast) oldToast.remove();
  
  const icons = {
    success: '✅',
    error: '❌',
    info: 'ℹ️',
    warning: '⚠️'
  };
  
  const colors = {
    success: { bg: '#6f9c92', shadow: 'rgba(111,156,146,0.4)' },
    error: { bg: '#dc2626', shadow: 'rgba(220,38,38,0.4)' },
    info: { bg: '#7aa79d', shadow: 'rgba(122,167,157,0.4)' },
    warning: { bg: '#f59e0b', shadow: 'rgba(245,158,11,0.4)' }
  };
  
  const color = colors[type] || colors.success;
  
  // Создаём новое
  const toast = document.createElement('div');
  toast.id = 'toast-notification';
  toast.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    padding: 18px 28px;
    background: ${color.bg};
    color: white;
    border-radius: 14px;
    font-weight: 700;
    font-size: 15px;
    box-shadow: 0 12px 48px ${color.shadow};
    z-index: 99999;
    display: flex;
    align-items: center;
    gap: 12px;
    animation: slideIn 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    max-width: 400px;
  `;
  toast.innerHTML = `
    <span style="font-size: 24px;">${icons[type] || '✅'}</span>
    <span>${message}</span>
  `;
  
  // Добавляем анимацию
  const style = document.createElement('style');
  style.textContent = `
    @keyframes slideIn {
      from { transform: translateX(500px); opacity: 0; }
      to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
      from { transform: translateX(0); opacity: 1; }
      to { transform: translateX(500px); opacity: 0; }
    }
    @media (max-width: 480px) {
      #toast-notification {
        left: 20px !important;
        right: 20px !important;
        max-width: none !important;
      }
    }
  `;
  if (!document.getElementById('toast-styles')) {
    style.id = 'toast-styles';
    document.head.appendChild(style);
  }
  
  document.body.appendChild(toast);
  
  // Убираем через 4 секунды
  setTimeout(() => {
    toast.style.animation = 'slideOut 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Уведомление о новой записи
function notifyAppointmentCreated(appointment, hospital) {
  const datetime = new Date(appointment.datetime);
  const message = `Запись создана! ${hospital.name}, ${datetime.toLocaleDateString('ru-RU')} в ${datetime.toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit'})}`;
  showToast(message, 'success');
  
  // Если браузер поддерживает уведомления
  if ('Notification' in window && Notification.permission === 'granted') {
    new Notification('MedQueue - Новая запись', {
      body: message,
      icon: '🏥',
      badge: '🏥'
    });
  }
}

// === PHONE WIDGET ===
const PHONE_REGIONS = [
  { code: '+7',   flag: '\uD83C\uDDF0\uD83C\uDDFF', name: '\u041a\u0430\u0437\u0430\u0445\u0441\u0442\u0430\u043d',  mask: '(___)\u00a0___-__-__' },
  { code: '+7',   flag: '\uD83C\uDDF7\uD83C\uDDFA', name: '\u0420\u043e\u0441\u0441\u0438\u044f',      mask: '(___)\u00a0___-__-__' },
  { code: '+375', flag: '\uD83C\uDDE7\uD83C\uDDFE', name: '\u0411\u0435\u043b\u0430\u0440\u0443\u0441\u044c',    mask: '(__)\u00a0___-__-__'  },
  { code: '+380', flag: '\uD83C\uDDFA\uD83C\uDDE6', name: '\u0423\u043a\u0440\u0430\u0438\u043d\u0430',     mask: '(__)\u00a0___-__-__'  },
  { code: '+998', flag: '\uD83C\uDDFA\uD83C\uDDFF', name: '\u0423\u0437\u0431\u0435\u043a\u0438\u0441\u0442\u0430\u043d',  mask: '(__)\u00a0___-__-__'  },
  { code: '+996', flag: '\uD83C\uDDF0\uD83C\uDDEC', name: '\u041a\u044b\u0440\u0433\u044b\u0437\u0441\u0442\u0430\u043d',  mask: '(___)\u00a0__-__-__'  },
];

function _maskPhoneInput(input) {
  const mask = input.dataset.phoneMask || '(___)\u00a0___-__-__';
  const digits = input.value.replace(/\D/g, '');
  let result = '', di = 0;
  for (let i = 0; i < mask.length && di < digits.length; i++) {
    result += (mask[i] === '_') ? digits[di++] : mask[i];
  }
  input.value = result;
}

function togglePhoneDropdown(ddId) {
  const dd = document.getElementById(ddId);
  if (!dd) return;
  const hidden = dd.style.display === 'none' || !dd.style.display;
  document.querySelectorAll('.phone-region-dropdown').forEach(d => d.style.display = 'none');
  if (hidden) dd.style.display = 'block';
}

function selectPhoneRegion(idx, prefix) {
  const r = PHONE_REGIONS[idx];
  const flagEl  = document.getElementById(prefix + 'PhoneFlag');
  const codeEl  = document.getElementById(prefix + 'PhoneCodeDisplay');
  const codeInp = document.getElementById(prefix + 'PhoneCode');
  const inp     = document.getElementById(prefix + 'Phone');
  const dd      = document.getElementById(prefix + 'RegionDrop');
  if (flagEl)  flagEl.textContent  = r.flag;
  if (codeEl)  codeEl.textContent  = r.code;
  if (codeInp) codeInp.value       = r.code;
  if (dd)      dd.style.display    = 'none';
  if (inp) {
    inp.dataset.phoneMask = r.mask;
    inp.placeholder       = r.mask;
    inp.value             = '';
    inp.focus();
  }
}

function initPhoneDropdowns() {
  document.querySelectorAll('.phone-region-dropdown').forEach(dd => {
    const prefix = dd.id.replace('RegionDrop', '');
    dd.innerHTML = PHONE_REGIONS.map((r, i) => `
      <div class="phone-region-opt" onclick="selectPhoneRegion(${i},'${prefix}');event.stopPropagation()">
        <span class="pr-flag">${r.flag}</span>
        <span class="pr-name">${r.name}</span>
        <span class="pr-code">${r.code}</span>
      </div>
    `).join('');
  });
  // Set default mask placeholder
  document.querySelectorAll('[data-phone-input]').forEach(inp => {
    inp.dataset.phoneMask = inp.dataset.phoneMask || PHONE_REGIONS[0].mask;
    inp.placeholder = inp.dataset.phoneMask;
    inp.addEventListener('input', function() { _maskPhoneInput(this); });
  });
  // Close on outside click
  document.addEventListener('click', function(e) {
    if (!e.target.closest('.phone-wrap')) {
      document.querySelectorAll('.phone-region-dropdown').forEach(d => d.style.display = 'none');
    }
  });
}

function _parseStoredPhone(stored, prefix) {
  if (!stored) return;
  const reg = PHONE_REGIONS.find(r => stored.startsWith(r.code + '\u00a0') || stored.startsWith(r.code + ' '));
  if (reg) {
    const idx = PHONE_REGIONS.indexOf(reg);
    selectPhoneRegion(idx, prefix);
    const inp = document.getElementById(prefix + 'Phone');
    if (inp) inp.value = stored.slice(reg.code.length + 1);
  } else {
    const inp = document.getElementById(prefix + 'Phone');
    if (inp) inp.value = stored;
  }
}

// Запросить разрешение на уведомления
function requestNotificationPermission() {
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission().then(permission => {
      if (permission === 'granted') {
        showToast('Уведомления включены!', 'success');
      }
    });
  }
}

function getDemoAppointments() {
  try {
    const raw = JSON.parse(localStorage.getItem(DEMO_APPOINTMENTS_KEY) || '{}');
    return raw && typeof raw === 'object' ? raw : {};
  } catch {
    return {};
  }
}

function saveDemoAppointments(map) {
  localStorage.setItem(DEMO_APPOINTMENTS_KEY, JSON.stringify(map || {}));
}

function generateCode(prefix = 'MQD') {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let out = prefix;
  for (let i = 0; i < 6; i++) out += chars[Math.floor(Math.random() * chars.length)];
  return out;
}

function createDemoAppointmentFromForm(payload) {
  const hospital = hospitals.find((h) => h.id === Number(payload.hospital));
  const q = Math.max(1, Math.min(18, Math.floor((hospital?.queue || 4) + Math.random() * 4)));
  const wait = Math.max(6, Math.min(120, q * 6));
  const datetime = payload.datetime || new Date(Date.now() + 2 * 3600 * 1000).toISOString();
  return {
    code: generateCode('MQD'),
    patient_name: payload.patient_name || 'Демо Пациент',
    hospital_name: hospital?.name || 'Демо клиника MedQueue',
    hospital_address: hospital?.address || 'Алматы, демонстрационный адрес',
    specialty: payload.specialty || 'Терапевт',
    queue_position: q,
    estimated_wait_time: wait,
    datetime,
    comment: payload.comment || '',
    created_at: Date.now(),
    demo: true,
  };
}

function saveDemoAppointment(appointment) {
  const map = getDemoAppointments();
  map[appointment.code] = appointment;
  saveDemoAppointments(map);
}

function getDemoAppointmentByCode(code) {
  const map = getDemoAppointments();
  return map[code] || null;
}

function computeLiveDemoQueue(appt) {
  const minutesPassed = Math.max(0, Math.floor((Date.now() - Number(appt.created_at || Date.now())) / 60000));
  const advanced = Math.floor(minutesPassed / 3);
  const q = Math.max(1, Number(appt.queue_position || 1) - advanced);
  const w = Math.max(3, q * 5);
  return {
    ...appt,
    queue_position: q,
    estimated_wait_time: w,
  };
}

function getDemoReminders() {
  try {
    const parsed = JSON.parse(localStorage.getItem(DEMO_REMINDERS_KEY) || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveDemoReminders(items) {
  localStorage.setItem(DEMO_REMINDERS_KEY, JSON.stringify(items));
}

function enqueueReminder(rem) {
  const all = getDemoReminders();
  all.push(rem);
  saveDemoReminders(all.slice(-30));
}

function processDueReminders() {
  const all = getDemoReminders();
  if (!all.length) return;
  const now = Date.now();
  let changed = false;
  all.forEach((r) => {
    if (r.fired) return;
    if (now >= Number(r.when || 0)) {
      showToast(r.text || 'Напоминание MedQueue', 'info');
      if ('Notification' in window && Notification.permission === 'granted') {
        new Notification('MedQueue - Напоминание', { body: r.text || 'Проверьте запись' });
      }
      const flow = getDemoFlowState();
      if (flow && Number(flow.step || 0) < 2) {
        flow.step = 2;
        flow.updated_at = Date.now();
        saveDemoFlowState(flow);
        renderDemoJourneyPanel();
      }
      r.fired = true;
      changed = true;
    }
  });
  if (changed) saveDemoReminders(all);
}

function scheduleReminderTimer(rem) {
  const delay = Number(rem.when || 0) - Date.now();
  if (delay <= 0 || delay > 24 * 3600 * 1000) return;
  setTimeout(() => processDueReminders(), delay + 150);
}

function scheduleAppointmentReminders(appointment, hospital, { demo = false } = {}) {
  const dt = new Date(appointment?.datetime || Date.now() + 3600000).getTime();
  const code = appointment?.code || 'N/A';
  const clinic = hospital?.name || appointment?.hospital_name || 'Клиника';

  const reminders = [
    {
      id: `${code}-t10s-${Date.now()}`,
      when: Date.now() + 10000,
      text: `Демо-напоминание: запись ${code} создана. Проверка готова к показу.`,
      fired: false,
    },
    {
      id: `${code}-t30m-${Date.now()}`,
      when: dt - 30 * 60 * 1000,
      text: `Через 30 минут прием в ${clinic}. Код записи: ${code}.`,
      fired: false,
    },
  ];

  reminders.forEach((r) => {
    if (r.when > Date.now() - 1000) {
      enqueueReminder(r);
      scheduleReminderTimer(r);
    }
  });

  showToast(demo ? 'Демо-напоминания поставлены (включая тест через 10с)' : 'Напоминания по записи активированы', 'success');
}

function renderQueueCompanion(appointment) {
  const host = document.getElementById('mqDemoShowcase');
  if (!host) return;

  const q = Number(appointment?.queue_position || 1);
  const wait = Number(appointment?.estimated_wait_time || Math.max(5, q * 6));
  const progress = Math.max(5, Math.min(100, 100 - q * 6));

  const queuePanel = host.querySelector('#mqQueueCompanion');
  if (queuePanel) {
    queuePanel.innerHTML = `
      <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap;">
        <strong>Ожидание в очереди</strong>
        <span style="font-size:12px;color:var(--muted);">Обновляется после проверки статуса</span>
      </div>
      <div style="margin-top:10px;font-size:14px;">Перед вами: <strong>${q}</strong> чел. • ожидание <strong>~${wait} мин</strong></div>
      <div style="height:8px;border-radius:999px;background:var(--border-soft);margin-top:8px;overflow:hidden;">
        <div style="height:100%;width:${progress}%;background:linear-gradient(90deg,#7aa79d,#6f9c92);"></div>
      </div>
    `;
  }
}

function getDemoFlowState() {
  try {
    const parsed = JSON.parse(localStorage.getItem(DEMO_FLOW_KEY) || 'null');
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

function saveDemoFlowState(state) {
  localStorage.setItem(DEMO_FLOW_KEY, JSON.stringify(state || null));
}

function seedDemoFlowFromAppointment(appointment) {
  const flow = {
    code: appointment?.code || generateCode('MQD'),
    patient_name: appointment?.patient_name || 'Пациент',
    hospital_name: appointment?.hospital_name || 'Клиника',
    specialty: appointment?.specialty || 'Терапевт',
    datetime: appointment?.datetime || new Date(Date.now() + 7200000).toISOString(),
    queue_position: Number(appointment?.queue_position || 6),
    estimated_wait_time: Number(appointment?.estimated_wait_time || 36),
    created_at: Number(appointment?.created_at || Date.now()),
    step: 1,
    updated_at: Date.now(),
  };
  saveDemoFlowState(flow);
  renderDemoJourneyPanel();
}

function formatStepTime(ts) {
  if (!ts) return '—';
  return new Date(ts).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

function renderDemoJourneyPanel() {
  const host = document.getElementById('mqJourneyPanel');
  if (!host) return;

  const flow = getDemoFlowState();
  if (!flow) {
    host.innerHTML = '<div style="font-size:13px;color:var(--muted);">Создайте запись, чтобы увидеть реалистичный путь пациента от регистрации до завершения приема.</div>';
    return;
  }

  const steps = [
    'Запись подтверждена',
    'Ожидание в очереди',
    'Напоминание отправлено',
    'Пациент на приеме',
    'Прием завершен',
  ];

  const activeStep = Math.max(0, Math.min(4, Number(flow.step || 0)));
  const progress = Math.round((activeStep / 4) * 100);
  const queueNow = Math.max(0, Number(flow.queue_position || 0) - activeStep);
  const waitNow = Math.max(0, Number(flow.estimated_wait_time || 0) - activeStep * 8);

  host.innerHTML = `
    <div style="display:grid;gap:10px;">
      <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap;">
        <strong>Путь пациента (реалистичный сценарий)</strong>
        <span style="padding:4px 9px;border-radius:999px;background:rgba(111,156,146,.16);font-size:12px;font-weight:700;">Код: ${flow.code}</span>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px;">
        <div style="padding:8px 10px;border:1px solid var(--border-soft);border-radius:8px;background:var(--card);font-size:12px;"><strong>Пациент:</strong> ${flow.patient_name}</div>
        <div style="padding:8px 10px;border:1px solid var(--border-soft);border-radius:8px;background:var(--card);font-size:12px;"><strong>Клиника:</strong> ${flow.hospital_name}</div>
        <div style="padding:8px 10px;border:1px solid var(--border-soft);border-radius:8px;background:var(--card);font-size:12px;"><strong>Спец.:</strong> ${flow.specialty}</div>
      </div>
      <div style="height:8px;border-radius:999px;background:var(--border-soft);overflow:hidden;"><div style="height:100%;width:${progress}%;background:linear-gradient(90deg,#6f9c92,#7aa79d);"></div></div>
      <div style="display:grid;gap:6px;">
        ${steps.map((label, idx) => {
          const done = idx <= activeStep;
          const mark = done ? '✔' : '○';
          return `<div style="font-size:13px;padding:7px 9px;border-radius:8px;border:1px solid ${done ? 'rgba(111,156,146,.45)' : 'var(--border-soft)'};background:${done ? 'rgba(111,156,146,.11)' : 'var(--card)'};">${mark} ${label}</div>`;
        }).join('')}
      </div>
      <div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;font-size:12px;color:var(--text-soft);">
        <span>Текущее ожидание: <strong>${waitNow} мин</strong></span>
        <span>Перед пациентом: <strong>${queueNow} чел</strong></span>
        <span>Обновлено: <strong>${formatStepTime(flow.updated_at)}</strong></span>
      </div>
    </div>
  `;
}

function initRecordingDemoShowcase() {
  if (!document.body.classList.contains('page-recording-avant')) return;
  const host = document.getElementById('mqDemoShowcase');
  if (!host || host.dataset.ready === '1') return;
  host.dataset.ready = '1';

  host.innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;">
      <article id="mqQueueCompanion" class="card" style="padding:12px;"></article>
      <article class="card" style="padding:12px;">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
          <strong>Напоминания</strong>
          <button type="button" id="mqReminderTest" class="btn btn-outline" style="font-size:12px;padding:6px 10px;">Тест через 10с</button>
        </div>
        <div id="mqReminderInfo" style="margin-top:10px;font-size:13px;color:var(--muted);">Создайте запись или нажмите тест, чтобы показать напоминание преподавателю.</div>
      </article>
      <article class="card" style="padding:12px;grid-column:1/-1;">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
          <strong>Реалистичный путь пациента</strong>
          <div>
            <button type="button" id="mqFlowNext" class="btn btn-outline" style="font-size:12px;padding:6px 10px;">Следующий этап</button>
            <button type="button" id="mqFlowReset" class="btn btn-outline" style="font-size:12px;padding:6px 10px;">Сброс</button>
          </div>
        </div>
        <div id="mqJourneyPanel" style="margin-top:10px;"></div>
      </article>
      <article class="card" style="padding:12px;grid-column:1/-1;">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
          <strong>Мини-игра «Очередь Runner» (офлайн)</strong>
          <div>
            <button type="button" id="mqGameStart" class="btn btn-primary" style="font-size:12px;padding:6px 10px;">Старт</button>
            <button type="button" id="mqGameRestart" class="btn btn-outline" style="font-size:12px;padding:6px 10px;">Рестарт</button>
          </div>
        </div>
        <div style="font-size:12px;color:var(--muted);margin:6px 0 10px;">Пробел/клик/тап = прыжок. Цель: переждать очередь и не врезаться в препятствия.</div>
        <canvas id="mqDinoCanvas" width="760" height="190" style="width:100%;max-width:100%;background:linear-gradient(180deg,#f8fffe,#eef6f4);border:1px solid var(--border-soft);border-radius:12px;"></canvas>
      </article>
    </div>
  `;

  renderQueueCompanion({ queue_position: 8, estimated_wait_time: 42 });
  renderDemoJourneyPanel();

  const testBtn = document.getElementById('mqReminderTest');
  const info = document.getElementById('mqReminderInfo');
  if (testBtn) {
    testBtn.addEventListener('click', () => {
      const reminder = {
        id: `manual-${Date.now()}`,
        when: Date.now() + 10000,
        text: 'Тест-напоминание MedQueue: проверьте очередь и подготовьте документы.',
        fired: false,
      };
      enqueueReminder(reminder);
      scheduleReminderTimer(reminder);
      if (info) info.textContent = 'Тест поставлен: через 10 секунд появится уведомление/toast.';
      showToast('Тест-напоминание запланировано на 10 секунд', 'info');
    });
  }

  initQueueRunnerGame();

  const flowNext = document.getElementById('mqFlowNext');
  const flowReset = document.getElementById('mqFlowReset');
  if (flowNext) {
    flowNext.addEventListener('click', () => {
      const flow = getDemoFlowState();
      if (!flow) {
        showToast('Сначала создайте запись, чтобы двигать этапы', 'info');
        return;
      }
      flow.step = Math.min(4, Number(flow.step || 0) + 1);
      flow.updated_at = Date.now();
      saveDemoFlowState(flow);
      renderDemoJourneyPanel();
      renderQueueCompanion(flow);
    });
  }
  if (flowReset) {
    flowReset.addEventListener('click', () => {
      localStorage.removeItem(DEMO_FLOW_KEY);
      renderDemoJourneyPanel();
      renderQueueCompanion({ queue_position: 8, estimated_wait_time: 42 });
      showToast('Демо-поток сброшен', 'success');
    });
  }

  const demoBtn = document.getElementById('demoBookingBtn');
  if (demoBtn) {
    demoBtn.addEventListener('click', () => {
      const hospitalId = Number(document.getElementById('hospitalSelectApp')?.value || 0);
      const specialty = document.getElementById('appSpecialty')?.value || 'Терапевт';
      const name = (document.getElementById('appName')?.value || '').trim() || 'Демо Пациент';
      const datetime = document.getElementById('appDatetime')?.value || new Date(Date.now() + 3 * 3600000).toISOString().slice(0, 16);
      const comment = (document.getElementById('appComment')?.value || '').trim();
      const payload = {
        patient_name: name,
        hospital: hospitalId || (hospitals[0]?.id || 1),
        specialty,
        datetime,
        comment,
      };
      const demo = createDemoAppointmentFromForm(payload);
      saveDemoAppointment(demo);
      rememberStatusLookup(demo.code, demo);
      renderStatusHistoryPanel();
      scheduleAppointmentReminders(demo, { name: demo.hospital_name }, { demo: true });
      seedDemoFlowFromAppointment(demo);
      const msgEl = document.getElementById('appMsg');
      if (msgEl) {
        msgEl.innerHTML = `
          <div style="margin-top:10px;padding:14px;border-radius:10px;border:1px solid #a3e635;background:linear-gradient(135deg,#f7fee7,#ecfccb);">
            <strong>Демо-запись создана:</strong> код <span style="font-family:monospace;font-size:18px;letter-spacing:2px;">${demo.code}</span>
            <div style="margin-top:8px;">Откройте «Проверка статуса очереди» и вставьте код, чтобы показать живое ожидание + игру.</div>
          </div>
        `;
      }
      const codeInput = document.getElementById('code');
      if (codeInput) codeInput.value = demo.code;
      renderQueueCompanion(demo);
      showToast('Офлайн демо-запись успешно создана', 'success');
    });
  }
}

function initQueueRunnerGame() {
  const canvas = document.getElementById('mqDinoCanvas');
  if (!canvas || canvas.dataset.ready === '1') return;
  canvas.dataset.ready = '1';

  const ctx = canvas.getContext('2d');
  const startBtn = document.getElementById('mqGameStart');
  const restartBtn = document.getElementById('mqGameRestart');

  const state = {
    running: false,
    gameOver: false,
    score: 0,
    speed: 4.4,
    gravity: 0.72,
    obstacles: [],
    t: 0,
    player: { x: 58, y: 0, w: 28, h: 42, vy: 0, jumpPower: 12.5 },
  };

  const SPRITES = {
    doctorA: [
      '..ssss..',
      '.skkkks.',
      '.swdwds.',
      '.swwwws.',
      '.swwwws.',
      '.sbbbbs.',
      '.sb..bs.',
      '.db..bd.',
    ],
    doctorB: [
      '..ssss..',
      '.skkkks.',
      '.swdwds.',
      '.swwwws.',
      '.swwwws.',
      '.sbbbbs.',
      '.s.bb.s.',
      '.db..bd.',
    ],
    queueEnemy: [
      '.rrrrr.',
      '.rkkkr.',
      '.rddddr.',
      '.rddddr.',
      '.ryyyyr.',
      '.ry..yr.',
      '.d....d.',
    ],
    queueEnemy2: [
      '.rrrrr.',
      '.rkkkr.',
      '.rddddr.',
      '.rddddr.',
      '.ryyyyr.',
      '.r.yy.r.',
      '.d....d.',
    ],
  };

  const PALETTE = {
    s: '#111827',
    k: '#f1c7a8',
    w: '#ffffff',
    b: '#3b82f6',
    d: '#0f172a',
    r: '#7f1d1d',
    y: '#f59e0b',
  };

  const PX = 4;

  function spriteSize(sprite) {
    return { w: (sprite[0] || '').length * PX, h: sprite.length * PX };
  }

  function drawSprite(sprite, x, y) {
    for (let row = 0; row < sprite.length; row++) {
      const line = sprite[row];
      for (let col = 0; col < line.length; col++) {
        const ch = line[col];
        if (ch === '.' || !PALETTE[ch]) continue;
        ctx.fillStyle = PALETTE[ch];
        ctx.fillRect(Math.round(x + col * PX), Math.round(y + row * PX), PX, PX);
      }
    }
  }

  const heroSize = spriteSize(SPRITES.doctorA);
  state.player.w = heroSize.w;
  state.player.h = heroSize.h;

  const groundY = () => canvas.height - 34;

  function resetGame() {
    state.running = false;
    state.gameOver = false;
    state.score = 0;
    state.speed = 4.4;
    state.obstacles = [];
    state.t = 0;
    state.player.y = groundY() - state.player.h;
    state.player.vy = 0;
    draw();
  }

  function jump() {
    if (state.gameOver) return;
    const onGround = state.player.y >= groundY() - state.player.h - 0.5;
    if (onGround) {
      state.player.vy = -state.player.jumpPower;
      state.running = true;
    }
  }

  function spawnObstacle() {
    const sprite = Math.random() > 0.5 ? SPRITES.queueEnemy : SPRITES.queueEnemy2;
    const size = spriteSize(sprite);
    state.obstacles.push({
      x: canvas.width + 10,
      y: groundY() - size.h,
      w: size.w,
      h: size.h,
      sprite,
      bob: Math.random() * 0.5,
    });
  }

  function intersects(a, b) {
    return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
  }

  function update() {
    if (!state.running || state.gameOver) return;
    state.t += 1;
    state.score += 1;
    if (state.score % 280 === 0) state.speed += 0.3;

    if (state.t % Math.max(36, 92 - Math.floor(state.speed * 8)) === 0) spawnObstacle();

    state.player.vy += state.gravity;
    state.player.y += state.player.vy;
    const floor = groundY() - state.player.h;
    if (state.player.y > floor) {
      state.player.y = floor;
      state.player.vy = 0;
    }

    state.obstacles.forEach((o) => { o.x -= state.speed; });
    state.obstacles = state.obstacles.filter((o) => o.x + o.w > -6);

    const playerBox = { x: state.player.x + 3, y: state.player.y + 2, w: state.player.w - 6, h: state.player.h - 3 };
    if (state.obstacles.some((o) => intersects(playerBox, o))) {
      state.gameOver = true;
      state.running = false;
      showToast(`Игра окончена. Счет: ${Math.floor(state.score / 8)}`, 'warning');
    }
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    ctx.fillStyle = '#dbeafe';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.fillStyle = '#6f9c92';
    ctx.fillRect(0, groundY(), canvas.width, 2);

    const p = state.player;
    const heroSprite = state.running && !state.gameOver && Math.floor(state.t / 8) % 2 === 0
      ? SPRITES.doctorA
      : SPRITES.doctorB;
    drawSprite(heroSprite, p.x, p.y);

    state.obstacles.forEach((o) => {
      const bobY = Math.sin((state.t + o.bob) * 0.08) * 1.5;
      drawSprite(o.sprite, o.x, o.y + bobY);
    });

    ctx.fillStyle = '#111827';
    ctx.font = '700 14px Inter, sans-serif';
    ctx.fillText(`Score: ${Math.floor(state.score / 8)}`, canvas.width - 120, 24);
    ctx.fillText('ГГ: доктор | Враги: очередь', 14, 24);

    if (!state.running && !state.gameOver) {
      ctx.fillStyle = '#1f2937';
      ctx.font = '700 16px Inter, sans-serif';
      ctx.fillText('Нажмите Старт и Прыжок (пробел/клик)', 16, 46);
    }
    if (state.gameOver) {
      ctx.fillStyle = '#7f1d1d';
      ctx.font = '800 20px Inter, sans-serif';
      ctx.fillText('GAME OVER', canvas.width / 2 - 62, 54);
    }
  }

  function loop() {
    update();
    draw();
    requestAnimationFrame(loop);
  }

  if (startBtn) startBtn.addEventListener('click', () => { state.running = true; state.gameOver = false; });
  if (restartBtn) restartBtn.addEventListener('click', resetGame);

  canvas.addEventListener('click', jump);
  document.addEventListener('keydown', (e) => {
    if (e.code === 'Space') {
      if (document.body.classList.contains('page-recording-avant')) {
        e.preventDefault();
        jump();
      }
    }
  });

  resetGame();
  loop();
}

function initInnovationLab() {
  const visitType = document.getElementById('labVisitType');
  const specialty = document.getElementById('labSpecialty');
  const dayPart = document.getElementById('labDayPart');
  const urgency = document.getElementById('labUrgency');
  const urgencyValue = document.getElementById('labUrgencyValue');
  const runBtn = document.getElementById('labRunBtn');
  const applyBtn = document.getElementById('labApplyBtn');
  const metaEl = document.getElementById('labScenarioMeta');

  if (!visitType || !dayPart || !urgency || !runBtn) return;

  const waitEl = document.getElementById('labWaitTime');
  const loadEl = document.getElementById('labLoadIndex');
  const slotEl = document.getElementById('labBestSlot');
  const hospitalEl = document.getElementById('labBestHospital');
  const onTimeEl = document.getElementById('labOnTime');
  const adviceEl = document.getElementById('labAdvice');
  const card = document.getElementById('labResultCard');
  let latestScenario = null;

  const recompute = () => {
    const baseByType = { plan: 20, soon: 15, urgent: 11 };
    const dayAdjustment = { morning: -2, day: 1, evening: 4 };
    const u = Number(urgency.value || 5);

    urgencyValue.textContent = String(u);

    // Higher urgency means stronger optimization, so expected wait decreases.
    const rawWait = (baseByType[visitType.value] || 16) + (dayAdjustment[dayPart.value] || 0) - Math.round(u * 1.05);
    const wait = Math.max(4, Math.min(32, rawWait));

    // Lower wait should generally correspond to lower load index.
    const load = Math.max(26, Math.min(95, Math.round(wait * 3 + (11 - u) * 1.2)));
    const onTime = Math.max(58, Math.min(98, Math.round(92 - wait * 0.9 + u * 0.7)));

    const slotsByDay = {
      morning: ['08:40 - 09:10', '09:20 - 09:50', '10:10 - 10:40'],
      day: ['12:40 - 13:10', '13:20 - 13:50', '14:10 - 14:40'],
      evening: ['17:20 - 17:50', '18:00 - 18:30', '18:40 - 19:10'],
    };
    const pick = slotsByDay[dayPart.value] || slotsByDay.day;
    const slot = pick[u >= 8 ? 0 : (u >= 5 ? 1 : 2)];

    let hospitalPick = null;
    if (Array.isArray(hospitals) && hospitals.length) {
      const ranked = [...hospitals].sort((a, b) => {
        const scoreA = Number(a.queue || 0) * 2 - Number(a.avgRating || 0) - u * 0.2;
        const scoreB = Number(b.queue || 0) * 2 - Number(b.avgRating || 0) - u * 0.2;
        return scoreA - scoreB;
      });
      hospitalPick = ranked[0] || null;
    }

    const adviceMap = {
      plan: u >= 7
        ? 'Плановый + высокий приоритет: система предложит более ранние окна с меньшей нагрузкой.'
        : 'Плановый сценарий: выбирайте удобный слот заранее и приходите за 10 минут.',
      soon: u >= 7
        ? 'Сценарий скоро: при высоком приоритете лучше подтверждать запись сразу, чтобы не терять окно.'
        : 'Сценарий скоро: держите документы под рукой и выбирайте слот с умеренной нагрузкой.',
      urgent: 'Срочный сценарий: берите ближайшее окно, подтверждение и выезд лучше не откладывать.',
    };

    waitEl.textContent = `~ ${wait} мин`;
    loadEl.textContent = `Load ${load}`;
    slotEl.textContent = slot;
    if (hospitalEl) hospitalEl.textContent = hospitalPick ? hospitalPick.name : 'Выберите клинику вручную';
    onTimeEl.textContent = `${onTime}%`;
    adviceEl.textContent = adviceMap[visitType.value] || adviceMap.plan;
    if (metaEl) {
      metaEl.textContent = `Сценарий: ${visitType.value} • ${dayPart.value} • приоритет ${u}/10 • специалист: ${specialty?.value || 'Терапевт'}`;
    }

    latestScenario = {
      hospitalId: hospitalPick ? String(hospitalPick.id) : '',
      mode: visitType.value === 'urgent' ? 'next' : (visitType.value === 'soon' ? 'fast' : 'balanced'),
      dayPart: dayPart.value,
      priority: u,
      specialty: specialty?.value || 'Терапевт',
    };

    if (card) {
      card.style.transform = 'scale(0.985)';
      setTimeout(() => { card.style.transform = 'scale(1)'; }, 120);
    }
  };

  urgency.addEventListener('input', recompute);
  visitType.addEventListener('change', recompute);
  dayPart.addEventListener('change', recompute);
  if (specialty) specialty.addEventListener('change', recompute);
  runBtn.addEventListener('click', recompute);

  if (applyBtn) {
    applyBtn.addEventListener('click', () => {
      if (!latestScenario) {
        recompute();
      }
      const s = latestScenario || {
        hospitalId: '', mode: 'balanced', dayPart: 'day', priority: 5, specialty: 'Терапевт'
      };

      try {
        localStorage.setItem(RECORDING_SCENARIO_KEY, JSON.stringify({ ...s, fromMainLab: true, ts: Date.now() }));
      } catch {}

      const q = new URLSearchParams({
        autoscenario: '1',
        mode: s.mode,
        day_part: s.dayPart,
        priority: String(s.priority),
        specialty: s.specialty,
      });
      if (s.hospitalId) q.set('hospital', s.hospitalId);
      window.location.href = `recording.html?${q.toString()}`;
    });
  }

  recompute();
}

function initMainQuickHospitalPicker() {
  const select = document.getElementById('heroHospitalSelect');
  const button = document.getElementById('heroHospitalBook');
  const detailsBtn = document.getElementById('heroHospitalDetails');
  const top = document.getElementById('heroTopHospitals');
  if (!select || !button || !top) return;

  const syncDetailsButton = () => {
    if (!detailsBtn) return;
    const hospitalId = select.value;
    if (!hospitalId) {
      detailsBtn.style.display = 'none';
      detailsBtn.setAttribute('href', '#');
      return;
    }
    detailsBtn.style.display = '';
    detailsBtn.setAttribute('href', `hospital.html?id=${hospitalId}`);
  };

  select.innerHTML = '<option value="">Выберите клинику</option>';
  hospitals.forEach((h) => {
    const opt = document.createElement('option');
    opt.value = String(h.id);
    opt.textContent = `${h.name} ${h.queue ? `(${h.queue} чел.)` : ''}`.trim();
    select.appendChild(opt);
  });

  const topHospitals = [...hospitals]
    .sort((a, b) => (b.avgRating || 0) - (a.avgRating || 0))
    .slice(0, 4);

  top.innerHTML = topHospitals.map((h) => `
    <article class="quick-hospital-card" data-hid="${h.id}">
      <div>
        <strong>${h.name}</strong>
        <small>Очередь: ${h.queue || 0} чел. • Рейтинг: ${(h.avgRating || 0).toFixed(1)}</small>
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end;">
        <button type="button" class="quick-hospital-pick">Выбрать</button>
        <a class="btn btn-outline" style="font-size:12px;padding:6px 10px;" href="hospital.html?id=${h.id}">Детали</a>
      </div>
    </article>
  `).join('');

  top.querySelectorAll('.quick-hospital-card .quick-hospital-pick').forEach((btn) => {
    btn.addEventListener('click', () => {
      const card = btn.closest('.quick-hospital-card');
      const hid = card?.getAttribute('data-hid') || '';
      select.value = hid;
      syncDetailsButton();
      select.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  });

  select.addEventListener('change', syncDetailsButton);
  syncDetailsButton();

  button.addEventListener('click', () => {
    const hospitalId = select.value;
    if (!hospitalId) {
      if (typeof showToast === 'function') showToast('Сначала выберите клинику', 'warning');
      else alert('Сначала выберите клинику');
      return;
    }
    window.location.href = `recording.html?hospital=${hospitalId}`;
  });
}

function initUnifiedPageExperience() {
  const body = document.body;
  if (!body) return;
  if (body.classList.contains('page-main-avant')) return;
  if (body.dataset.skipUnifiedHero === '1') return;

  const main = document.querySelector('main');
  if (!main || main.querySelector('.mq-page-hero')) return;

  const pageConfig = [
    {
      className: 'page-recording-avant',
      title: 'Запись без лишних шагов',
      subtitle: 'Выберите клинику, врача и время. Форма подскажет ошибки и сохранит черновик.',
      actions: [
        { href: 'doctors.html', label: 'Выбрать врача' },
        { href: 'recording.html#status-check', label: 'Проверить статус' },
      ],
    },
    {
      className: 'page-status-avant',
      title: 'Контроль очереди в реальном времени',
      subtitle: 'Введите код записи и получите актуальный статус, время и следующие шаги.',
      actions: [
        { href: 'recording.html', label: 'Новая запись' },
        { href: 'profile.html', label: 'Открыть кабинет' },
      ],
    },
    {
      className: 'page-profile-avant',
      title: 'Ваш медицинский кабинет',
      subtitle: 'История, записи, отзывы и персональные данные в одном месте.',
      actions: [
        { href: 'recording.html', label: 'Записаться снова' },
        { href: 'subscription.html', label: 'Подписка Plus' },
      ],
    },
    {
      className: 'page-doctors-avant',
      title: 'Каталог врачей с отзывами',
      subtitle: 'Фильтруйте специалистов по направлению, рейтингу и клинике.',
      actions: [
        { href: 'recording.html', label: 'Перейти к записи' },
        { href: 'hospital.html', label: 'Клиники' },
      ],
    },
    {
      className: 'page-hospital-avant',
      title: 'Клиники и нагрузка по приему',
      subtitle: 'Сравните загрузку отделений и выберите подходящее место приема.',
      actions: [
        { href: 'recording.html', label: 'Записаться' },
        { href: 'doctors.html', label: 'Список врачей' },
      ],
    },
    {
      className: 'page-auth-avant',
      title: 'Безопасный вход и регистрация',
      subtitle: 'Создайте аккаунт или войдите, чтобы управлять записями и очередью.',
      actions: [
        { href: 'main.html', label: 'На главную' },
        { href: 'subscription.html', label: 'Преимущества Plus' },
      ],
    },
    {
      className: 'page-subscription-avant',
      title: 'Подписка для приоритетного сервиса',
      subtitle: 'Сокращайте ожидание, получайте напоминания и расширенные возможности.',
      actions: [
        { href: 'recording.html', label: 'Начать запись' },
        { href: 'contacts and about.html', label: 'Задать вопрос' },
      ],
    },
    {
      className: 'page-contacts-avant',
      title: 'О сервисе и контакты',
      subtitle: 'Свяжитесь с командой и узнайте, как работает MedQueue внутри.',
      actions: [
        { href: 'main.html', label: 'Главная' },
        { href: 'subscription.html', label: 'Подписка' },
      ],
    },
    {
      className: 'page-doctor-avant',
      title: 'Кабинет врача',
      subtitle: 'Рабочий поток по пациентам, статусам и расписанию в одной панели.',
      actions: [
        { href: 'recording.html', label: 'Записи' },
        { href: 'profile.html', label: 'Профиль' },
      ],
    },
    {
      className: 'page-admin-avant',
      title: 'Панель администратора',
      subtitle: 'Управление пользователями, врачами и операционными показателями системы.',
      actions: [
        { href: 'main.html', label: 'Сайт' },
        { href: 'hospital.html', label: 'Клиники' },
      ],
    },
  ];

  const cfg = pageConfig.find((item) => body.classList.contains(item.className));
  if (!cfg) return;

  const hero = document.createElement('section');
  hero.className = 'mq-page-hero';

  const actionsHtml = (cfg.actions || []).map((a) => (
    `<a class="btn btn-outline mq-page-hero-action" href="${a.href}">${a.label}</a>`
  )).join('');

  const user = getCurrentUser();
  const firstName = user?.name ? String(user.name).split(' ')[0] : 'Пользователь';
  const metrics = `
    <div class="mq-page-hero-metrics">
      <article><strong>${hospitals.length || 0}</strong><span>клиник в системе</span></article>
      <article><strong>${(myAppointments || []).length || 0}</strong><span>ваших записей</span></article>
      <article><strong>${new Date().toLocaleDateString('ru-RU')}</strong><span>текущая дата</span></article>
    </div>
  `;

  hero.innerHTML = `
    <div class="mq-page-hero-left">
      <div class="mq-page-hero-kicker">MedQueue Flow</div>
      <h1>${cfg.title}</h1>
      <p>${cfg.subtitle}</p>
      <div class="mq-page-hero-actions">${actionsHtml}</div>
    </div>
    <div class="mq-page-hero-right">
      <div class="mq-page-hero-user">Здравствуйте, ${firstName}</div>
      ${metrics}
    </div>
  `;

  hero.classList.add('revealed');

  main.insertBefore(hero, main.firstChild);
}

function initSmartFormDrafts() {
  const forms = Array.from(document.querySelectorAll('form'));
  if (!forms.length) return;

  const page = (window.location.pathname.split('/').pop() || 'main.html').toLowerCase();

  const getFieldKey = (el, idx) => el.name || el.id || `field_${idx}`;
  const isSkippable = (el) => {
    const t = (el.type || '').toLowerCase();
    return t === 'password' || t === 'hidden' || t === 'file' || t === 'submit' || t === 'button';
  };

  forms.forEach((form, fIdx) => {
    const formId = form.id || `form_${fIdx}`;
    const storageKey = `medqueue_draft_${page}_${formId}`;
    const fields = Array.from(form.querySelectorAll('input, select, textarea')).filter((el) => !isSkippable(el));
    if (!fields.length) return;

    try {
      const raw = localStorage.getItem(storageKey);
      if (raw) {
        const saved = JSON.parse(raw);
        fields.forEach((el, idx) => {
          const key = getFieldKey(el, idx);
          if (!(key in saved)) return;
          if (el.type === 'checkbox' || el.type === 'radio') {
            el.checked = Boolean(saved[key]);
          } else {
            el.value = saved[key];
          }
        });
      }
    } catch {
      // ignore malformed storage payload
    }

    let timer = null;
    const saveDraft = () => {
      const payload = {};
      fields.forEach((el, idx) => {
        const key = getFieldKey(el, idx);
        payload[key] = (el.type === 'checkbox' || el.type === 'radio') ? Boolean(el.checked) : el.value;
      });
      localStorage.setItem(storageKey, JSON.stringify(payload));
    };

    const debouncedSave = () => {
      clearTimeout(timer);
      timer = setTimeout(saveDraft, 220);
    };

    fields.forEach((el) => {
      el.addEventListener('input', debouncedSave);
      el.addEventListener('change', debouncedSave);
    });

    form.addEventListener('submit', () => {
      localStorage.removeItem(storageKey);
    });
  });
}

