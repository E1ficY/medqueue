// === НАСТРОЙКИ API ===
const DEFAULT_LOCAL_API_ORIGIN = 'http://127.0.0.1:8001';
const API_BASE = window.location.protocol === 'file:'
  ? (localStorage.getItem('medqueue_api_origin') || DEFAULT_LOCAL_API_ORIGIN)
  : window.location.origin;
const API_URL = `${API_BASE}/api`;
const AUTH_STORAGE_KEY = 'medqueue_current_user';

// === ДАННЫЕ ===
let hospitals = [];
let myAppointments = [];
let selectedType = 'all'; // Фильтр по типу клиник

// === ИНИЦИАЛИЗАЦИЯ ===
document.addEventListener('DOMContentLoaded', async function() {
  updateAuthNav();

  // Запрашиваем разрешение на уведомления
  setTimeout(requestNotificationPermission, 2000);
  
  // Проверяем авторизацию на главной странице
  if (window.location.pathname.includes('main.html') || window.location.pathname.includes('index.html')) {
    checkAuthForMainPage();
  }
  
  await loadHospitals();
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
                style="flex: 1; padding: 16px; background: linear-gradient(135deg, #16a34a, #15803d); color: white; border: none; border-radius: 12px; font-weight: 700; font-size: 16px; cursor: pointer;">
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
const HOSPITALS_CACHE_KEY = 'medqueue_hospitals_cache';
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
    const response = await fetch(`${API_URL}/hospitals/`);
    if (!response.ok) throw new Error('API error');
    const data = await response.json();
    hospitals = data.map(h => ({
      id: h.id,
      name: h.name,
      type: h.type,
      address: h.address,
      waiting: h.waiting_time,
      queue: h.current_queue
    }));
    // Сохраняем в кэш
    try {
      localStorage.setItem(HOSPITALS_CACHE_KEY, JSON.stringify({ ts: Date.now(), data: hospitals }));
    } catch(e) {}
  } catch (error) {
    console.error('Ошибка загрузки больниц:', error);
    // Если API не работает, пытаемся взять устаревший кэш
    try {
      const stale = JSON.parse(localStorage.getItem(HOSPITALS_CACHE_KEY) || 'null');
      if (stale) { hospitals = stale.data; return; }
    } catch(e) {}
    hospitals = [
      {id: 1, name: "Городская поликлиника №1", type: "Поликлиника", address: "ул. Абая, 45", waiting: 12, queue: 5}
    ];
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
  const html = filtered.map(h => `
    <div class="card">
      <div class="title">${h.name}</div>
      <div class="meta">📍 ${h.address || h.type}</div>
      <div class="tag">${h.type}</div>
      <div class="queue">
        Очередь:
        <span class="badge">${h.queue || 0} чел.</span>
      </div>
      <div style="margin-top:8px; color:var(--muted); font-size:13px;">
        Ожидание: ~${h.waiting} мин
      </div>
      <button class="btn btn-primary" style="width:100%; margin-top:12px" onclick="quickBook(${h.id})">
        Записаться
      </button>
    </div>
  `).join('');

  // Одно обновление DOM
  container.innerHTML = html;
}

// === ФИЛЬТР ПО ТИПУ КЛИНИК ===
function filterByType(type) {
  selectedType = type;
  
  // Обновляем активную кнопку
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.classList.remove('active');
  });
  event.target.classList.add('active');
  
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
    
    // Предзаполнение из URL параметров
    const params = new URLSearchParams(window.location.search);
    const hospitalId = params.get('hospital');
    if (hospitalId) {
      const select = document.getElementById('hospitalSelectApp');
      if (select) select.value = hospitalId;
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
    const response = await fetch(`${API_URL}/appointments/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        patient_name: 'Гость',
        hospital: parseInt(hospitalId),
        specialty: specialty,
        datetime: datetime
      })
    });
    
    if (!response.ok) throw new Error('Ошибка создания записи');
    
    const appointment = await response.json();
    const hospital = hospitals.find(h => h.id === parseInt(hospitalId));
    
    // Уведомление
    notifyAppointmentCreated(appointment, hospital);
    
    // Показываем большое окно с кодом
    msgEl.innerHTML = `
      <div style="margin-top:16px; padding:16px; background:linear-gradient(135deg, #dcfce7 0%, #d1fae5 100%); border-radius:10px; border:2px solid #16a34a;">
        <div style="text-align:center;">
          <div style="font-size:18px; margin-bottom:8px;">🎉 Вы записаны!</div>
          <div style="font-size:13px; color:#166534; margin-bottom:12px;">Сохраните код</div>
          <div style="background:white; padding:12px; border-radius:8px; margin-bottom:12px;">
            <div style="font-size:11px; color:#6b7280; margin-bottom:4px;">КОД ЗАПИСИ</div>
            <div style="font-size:28px; font-weight:900; color:#16a34a; letter-spacing:3px; font-family:monospace;">
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
    showMessage(msgEl, '❌ Ошибка создания записи. Проверьте подключение к серверу.', 'error');
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
  const msgEl      = document.getElementById('appMsg');
  
  if (!name || !hospitalId || !datetime) {
    showMessage(msgEl, '❌ Заполните все поля', 'error');
    return;
  }
  
  // Отправляем на API
  try {
    const response = await fetch(`${API_URL}/appointments/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        patient_name: name,
        phone: phone || undefined,
        hospital: parseInt(hospitalId),
        specialty: specialty,
        datetime: datetime
      })
    });
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.datetime ? errorData.datetime[0] : 'Ошибка создания записи');
    }
    
    const appointment = await response.json();
    const hospital = hospitals.find(h => h.id === parseInt(hospitalId));
    
    // Показываем большое окно с кодом
    msgEl.innerHTML = `
      <div style="margin-top:16px; padding:20px; background:linear-gradient(135deg, #dcfce7 0%, #d1fae5 100%); border-radius:12px; border:2px solid #16a34a;">
        <div style="text-align:center; margin-bottom:16px;">
          <div style="font-size:24px; margin-bottom:8px;">🎉 Запись подтверждена!</div>
          <div style="font-size:14px; color:#166534; margin-bottom:16px;">Сохраните код для проверки статуса очереди</div>
        </div>
        
        <div style="background:white; padding:16px; border-radius:10px; margin-bottom:16px;">
          <div style="text-align:center;">
            <div style="font-size:13px; color:#6b7280; margin-bottom:8px; font-weight:600;">ВАШ КОД ЗАПИСИ</div>
            <div style="font-size:36px; font-weight:900; color:#16a34a; letter-spacing:4px; font-family:monospace;">
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
          <div style="margin-bottom:6px;"><strong>Врач:</strong> ${specialty}</div>
          <div style="margin-bottom:6px;"><strong>Дата:</strong> ${new Date(datetime).toLocaleString('ru-RU')}</div>
          <div><strong>Место в очереди:</strong> ${appointment.queue_position}</div>
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
            <div style="width:48px; height:48px; background:#16a34a; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:24px;">
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
              </div>
              
              <div style="border-top:1px solid #e5e7eb; padding-top:12px;">
                <div style="font-size:12px; color:#6b7280; margin-bottom:4px;">ДАТА И ВРЕМЯ</div>
                <div style="font-weight:600; color:#111827;">
                  🕐 ${datetime.toLocaleDateString('ru-RU')} в ${datetime.toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit'})}
                </div>
              </div>
            </div>
          </div>
          
          <div style="background:#dcfce7; padding:16px; border-radius:10px; border:1px solid #86efac; margin-bottom:12px;">
            <div style="text-align:center;">
              <div style="font-size:13px; color:#166534; margin-bottom:6px; font-weight:600;">ВАШЕ МЕСТО В ОЧЕРЕДИ</div>
              <div style="font-size:42px; font-weight:900; color:#15803d; line-height:1;">${appointment.queue_position}</div>
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
  element.style.color = type === 'error' ? '#dc2626' : type === 'success' ? '#16a34a' : '#6b7280';
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
    success: { bg: '#16a34a', shadow: 'rgba(22,163,74,0.4)' },
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