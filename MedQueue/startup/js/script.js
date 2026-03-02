// === НАСТРОЙКИ API ===
const DEFAULT_LOCAL_API_ORIGIN = 'http://127.0.0.1:8000';
const API_BASE = window.location.protocol === 'file:'
  ? (localStorage.getItem('medqueue_api_origin') || DEFAULT_LOCAL_API_ORIGIN)
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

// === ЗАЩИТА СТРАНИЦ ПО РОЛИ ===
// Страницы для пациентов (врачи и админы сюда не должны попадать)
const PATIENT_PAGES = ['main.html', 'index.html', 'profile.html', 'recording.html', 'status.html', 'hospital.html'];
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
  // Защита по роли — выполняется первой
  enforceRoleAccess();

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
  initHospitalSelects();
  renderHospitalCards();
  initSearch();
  initForms();
  initStatusPage();
  highlightActiveNav();
  initPhoneDropdowns();
});

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
                style="flex: 1; padding: 16px; background: linear-gradient(135deg, #0f172a, #14b8a6); color: white; border: none; border-radius: 12px; font-weight: 700; font-size: 16px; cursor: pointer;">
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
const HOSPITALS_CACHE_KEY = 'medqueue_hospitals_cache_v5'; // v5 — restored 20 hospitals, 46 doctors
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
      queue:       h.current_queue,
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
    return;
  }

  // Буферизация через DocumentFragment — один рефлоу вместо многих
  const TYPE_COLORS = {
    'Поликлиника': '#14b8a6', 'Больница': '#3b82f6',
    'Детская': '#f59e0b',     'Спец. клиника': '#8b5cf6',
  };
  const TYPE_ICONS = {
    'Поликлиника': '🏥', 'Больница': '🏨',
    'Детская': '👶',     'Спец. клиника': '🔬',
  };

  const html = filtered.map(h => {
    const color  = TYPE_COLORS[h.type] || '#14b8a6';
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
        <div style="font-size:12px;color:var(--text-muted)">⏱ Ожидание ~${h.waiting} мин</div>
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
}

// === ФИЛЬТР ПО ТИПУ КЛИНИК ===
function filterByType(type, evt) {
  selectedType = type;
  
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
  }
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
      <div style="margin-top:16px; padding:16px; background:linear-gradient(135deg, #f0fdfa 0%, #ccfbf1 100%); border-radius:10px; border:2px solid #14b8a6;">
        <div style="text-align:center;">
          <div style="font-size:18px; margin-bottom:8px;">🎉 Вы записаны!</div>
          <div style="font-size:13px; color:#0f766e; margin-bottom:12px;">Сохраните код</div>
          <div style="background:white; padding:12px; border-radius:8px; margin-bottom:12px;">
            <div style="font-size:11px; color:#6b7280; margin-bottom:4px;">КОД ЗАПИСИ</div>
            <div style="font-size:28px; font-weight:900; color:#14b8a6; letter-spacing:3px; font-family:monospace;">
              ${appointment.code}
            </div>
          </div>
          <div style="font-size:12px; margin-bottom:8px;">
            <strong>${hospital.name}</strong><br>
            ${specialty} • ${new Date(datetime).toLocaleDateString('ru-RU')}<br>
            Место в очереди: <strong>${appointment.queue_position}</strong>
          </div>
          <a href="status.html" class="btn btn-primary" style="font-size:12px; padding:6px 12px;">Проверить статус</a>
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

  try {
    const response = await authFetch(`${API_URL}/appointments/`, {
      method: 'POST',
      body: JSON.stringify({
        patient_name: name,
        phone: phone || undefined,
        hospital: parseInt(hospitalId),
        specialty: specialty,
        doctor: doctorId,
        datetime: datetime
      })
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
      <div style="margin-top:16px; padding:20px; background:linear-gradient(135deg, #f0fdfa 0%, #ccfbf1 100%); border-radius:12px; border:2px solid #14b8a6;">
        <div style="text-align:center; margin-bottom:16px;">
          <div style="font-size:24px; margin-bottom:8px;">🎉 Запись подтверждена!</div>
          <div style="font-size:14px; color:#0f766e; margin-bottom:16px;">Сохраните код для проверки статуса очереди</div>
        </div>
        
        <div style="background:white; padding:16px; border-radius:10px; margin-bottom:16px;">
          <div style="text-align:center;">
            <div style="font-size:13px; color:#6b7280; margin-bottom:8px; font-weight:600;">ВАШ КОД ЗАПИСИ</div>
            <div style="font-size:36px; font-weight:900; color:#14b8a6; letter-spacing:4px; font-family:monospace;">
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
          ${comment ? `<div style="margin-top:2px;padding:8px 10px;background:rgba(0,0,0,0.04);border-radius:6px;border-left:3px solid #14b8a6;"><strong>Комментарий:</strong> ${comment}</div>` : ''}
        </div>
        
        <div style="margin-top:12px; text-align:center;">
          <a href="status.html" class="btn btn-primary">Проверить статус очереди</a>
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
    
    // Прокрутка к сообщению
    msgEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    
  } catch (error) {
    console.error('Ошибка:', error);
    showMessage(msgEl, `❌ ${error.message}`, 'error');
  }
}

// === ПРОВЕРКА СТАТУСА ===
function initStatusPage() {
  const checkForm = document.getElementById('checkForm');
  if (!checkForm) return;
  
  // Проверяем URL параметры (если перешли из личного кабинета)
  const params = new URLSearchParams(window.location.search);
  const codeFromUrl = params.get('code');
  
  if (codeFromUrl) {
    const codeInput = document.getElementById('code');
    if (codeInput) {
      codeInput.value = codeFromUrl;
      // Автоматически проверяем
      checkForm.dispatchEvent(new Event('submit'));
    }
  }
  
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
      const datetime = new Date(appointment.datetime);
      const waitTime = appointment.estimated_wait_time;
      
      resultDiv.style.display = 'block';
      resultDiv.innerHTML = `
        <div style="padding:20px; background:linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%); border-radius:12px; border:2px solid #3b82f6;">
          <div style="display:flex; align-items:center; gap:12px; margin-bottom:16px;">
            <div style="width:48px; height:48px; background:linear-gradient(135deg,#0f172a,#14b8a6); border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:24px;">
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
            </div>
          </div>
          
          <div style="background:#f0fdfa; padding:16px; border-radius:10px; border:1px solid #5eead4; margin-bottom:12px;">
            <div style="text-align:center;">
              <div style="font-size:13px; color:#0f766e; margin-bottom:6px; font-weight:600;">ВАШЕ МЕСТО В ОЧЕРЕДИ</div>
              <div style="font-size:42px; font-weight:900; color:#0d9488; line-height:1;">${appointment.queue_position}</div>
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
          
          <button class="btn btn-outline" style="width:100%;" onclick="cancelAppointment('${appointment.code}')">
            Отменить запись
          </button>
        </div>
      `;
      
    } catch (error) {
      console.error('Ошибка:', error);
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
        <div style="padding:16px; background:#dcfce7; border-radius:10px; border:1px solid #86efac; color:#166534;">
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
  element.style.color = type === 'error' ? '#dc2626' : type === 'success' ? '#14b8a6' : '#6b7280';
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
    success: { bg: '#14b8a6', shadow: 'rgba(20,184,166,0.4)' },
    error: { bg: '#dc2626', shadow: 'rgba(220,38,38,0.4)' },
    info: { bg: '#3b82f6', shadow: 'rgba(59,130,246,0.4)' },
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