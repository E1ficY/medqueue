# MedQueue 🏥 — Version 6.0

> Система электронной очереди в медицинские учреждения Алматы.
> **v6.0** — Production-ready: Docker, SSL, OAuth, Redis-кэш, Celery, OWASP-безопасность.

🌐 **Live:** https://medqueue.me

---

## Стек технологий

### Backend
| Компонент | Версия | Назначение |
|-----------|--------|------------|
| Python | 3.12 | Язык |
| Django | 5.0 | Web-фреймворк |
| Django REST Framework | 3.14 | REST API |
| SimpleJWT | 5.x | JWT авторизация |
| Gunicorn | 26.0 | WSGI-сервер (4 workers) |
| PostgreSQL | 15 | База данных |
| Redis | 7 | Кэш + Celery broker |
| Celery | 5.6 | Асинхронные задачи (concurrency=4) |
| django-redis | 6.0 | Django-кэш через Redis |
| django-csp | 3.8 | Content-Security-Policy |
| django-cors-headers | 4.x | CORS |

### Frontend
| Компонент | Описание |
|-----------|----------|
| HTML5 / CSS3 / Vanilla JS | Статические страницы без фреймворков |
| **2ГИС MapGL JS API** | Интерактивная карта с маркерами клиник |
| **МедAI** | ИИ-ассистент (Kimi-K2 → Gemini 1.5 Flash) |
| Google Fonts — Inter | Шрифт |
| Cloudflare Turnstile | CAPTCHA на регистрации |

### Инфраструктура
| Компонент | Описание |
|-----------|----------|
| Docker + Docker Compose | Контейнеризация |
| Nginx | SSL-терминатор, reverse proxy |
| Let's Encrypt | SSL-сертификат |
| Cloudflare | CDN, DDoS-защита |
| DigitalOcean | VPS (46.101.126.48) |

---

## Роли пользователей

### 👤 Неавторизованный (гость)
Доступно без токена:
- `GET /api/hospitals/` — список больниц (кэш Redis)
- `GET /api/hospitals/{id}/` — карточка больницы
- `GET /api/hospitals/{id}/doctors/` — врачи по специальностям
- `GET /api/doctors/` — каталог врачей
- `POST /api/auth/register/` — регистрация
- `POST /api/auth/login/` — вход
- `POST /api/auth/google/` — вход через Google
- `POST /api/auth/facebook/` — вход через Facebook

### 🙋 Пациент (`role: patient`)
Всё что доступно гостю +
- `GET /api/appointments/` — **только свои** записи
- `POST /api/appointments/` — создать запись
- `PATCH /api/appointments/{id}/` — изменить **только свою** запись
- `DELETE /api/appointments/{id}/` — отменить **только свою** запись
- `GET /profile.html` — личный кабинет
- `POST /api/subscription/...` — управление подпиской

### 🩺 Врач (`role: doctor`)
Всё что пациент +
- `GET /api/doctor/me/` — свой профиль врача
- `GET /api/doctor/appointments/` — записи к себе
- `PATCH /api/doctor/appointments/{id}/` — изменить статус приёма
- `POST /api/doctor/appointments/{id}/recommendation/` — написать рекомендацию
- `POST /api/doctor/appointments/{id}/prescription/` — выписать рецепт
- Доступ к `doctor.html` с расширенным интерфейсом

### 🔑 Администратор (`role: admin`)
Всё что врач +
- `GET /api/admin/stats/` — статистика системы
- `GET /api/admin/hospitals/` — управление больницами
- `GET /api/admin/doctors/` — управление врачами
- `POST /api/admin/invite-codes/` — создание кодов для врачей
- `GET /api/admin/users/` — список пользователей
- `GET /admin/` — Django Admin панель

> **Проверка ролей:** `GET /api/admin/stats/` без токена → **401**, с токеном пациента → **403**, с токеном admin → **200** ✅

---

## Безопасность

### Аутентификация
- JWT (access + refresh токены)
- Google OAuth 2.0 implicit flow
- Email OTP-код при регистрации (6 цифр, 10 мин)
- Rate-limit: блокировка IP после N неудачных попыток (Redis)

### OWASP
| Уязвимость | Защита |
|------------|--------|
| A01 Broken Access Control | `filter(user=request.user)` + `_require_admin()` |
| A03 Injection | Только Django ORM, нет `.raw()` / `cursor.execute()` |
| A07 Auth Failures | Логирование + блокировка по IP через Redis |

### HTTP-заголовки
```
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' https://challenges.cloudflare.com; ...
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
Cross-Origin-Opener-Policy: same-origin
```

---

## Redis-кэш (доказательство ускорения)

Публичные эндпоинты кэшируются на **60 секунд**. Заголовок `X-Cache` показывает источник:

```
1-й запрос → GET /api/hospitals/  →  X-Cache: MISS  (~150ms, PostgreSQL)
2-й запрос → GET /api/hospitals/  →  X-Cache: HIT   (~3ms,   Redis)
```

| Эндпоинт | Cache Key | TTL |
|----------|-----------|-----|
| `GET /api/hospitals/` | `hospitals:list` | 60s |
| `GET /api/hospitals/{id}/` | `hospitals:detail:{id}` | 60s |
| `GET /api/hospitals/{id}/doctors/` | `hospitals:doctors:{id}` | 60s |

---

## Celery — асинхронные задачи

**До v6:** регистрация ждала SMTP 1–3 сек  
**После v6:** HTTP 200 мгновенно, письмо уходит в фоне

```
POST /api/auth/register/ → 200 OK (мгновенно)
                        ↓
                  [Celery Worker × 4]
                  send_email_async.delay() → SMTP → Inbox
```

| Задача | Назначение |
|--------|-----------|
| `send_email_async` | Асинхронная отправка email |
| `long_task` | Демо-задача для тестирования |
| `invalidate_cache_prefix` | Инвалидация Redis-кэша |

---

## API-эндпоинты

### Публичные (без токена)
| Метод | URL | Описание |
|-------|-----|----------|
| `GET` | `/api/hospitals/` | Список больниц (кэш 60s) |
| `GET` | `/api/hospitals/{id}/` | Карточка больницы (кэш) |
| `GET` | `/api/hospitals/{id}/doctors/` | Врачи по специальностям (кэш) |
| `GET` | `/api/doctors/` | Каталог врачей |
| `POST` | `/api/auth/register/` | Регистрация + CAPTCHA |
| `POST` | `/api/auth/login/` | Вход → JWT |
| `POST` | `/api/auth/verify/` | Подтверждение OTP |
| `POST` | `/api/auth/google/` | Вход через Google → JWT |
| `POST` | `/api/auth/facebook/` | Вход через Facebook → JWT |
| `POST` | `/api/auth/password-reset/` | Сброс пароля |

### Пациент (JWT required)
| Метод | URL | Описание |
|-------|-----|----------|
| `GET/POST` | `/api/appointments/` | Свои записи |
| `GET/PATCH/DELETE` | `/api/appointments/{id}/` | Конкретная запись (только своя) |
| `GET` | `/api/subscription/me/` | Моя подписка |
| `POST` | `/api/subscription/activate/` | Активировать подписку |

### Врач (JWT + role=doctor)
| Метод | URL | Описание |
|-------|-----|----------|
| `GET` | `/api/doctor/me/` | Профиль врача |
| `GET` | `/api/doctor/appointments/` | Записи к врачу |
| `PATCH` | `/api/doctor/appointments/{id}/` | Изменить статус |
| `POST` | `/api/doctor/appointments/{id}/recommendation/` | Рекомендации |

### Администратор (JWT + role=admin)
| Метод | URL | Описание |
|-------|-----|----------|
| `GET` | `/api/admin/stats/` | Статистика |
| `GET/POST` | `/api/admin/hospitals/` | Больницы |
| `GET/POST` | `/api/admin/doctors/` | Врачи |
| `GET/POST` | `/api/admin/invite-codes/` | Коды для врачей |
| `GET` | `/api/admin/users/` | Пользователи |

---

## Структура проекта

```
MedQueue/
├── README.md
├── CHANGELOG.md
├── startup/
│   ├── docker-compose.yml          # Docker Compose (backend, worker, nginx, redis, db)
│   ├── backend/
│   │   ├── requirements.txt
│   │   ├── .env                    # Секреты (не в git)
│   │   ├── .gitignore              # .env, .env.* исключены
│   │   ├── appointments/
│   │   │   ├── models.py           # Hospital, Doctor, Appointment, UserProfile...
│   │   │   ├── views.py            # CRUD + Redis-кэш + X-Cache header
│   │   │   ├── auth_views.py       # Регистрация, вход, Google/Facebook OAuth
│   │   │   ├── tasks.py            # Celery: send_email_async, long_task
│   │   │   ├── security.py         # Rate-limit, блокировка по IP (Redis)
│   │   │   ├── permissions.py      # IsAdminRole, IsResourceOwnerOrAdmin
│   │   │   ├── throttles.py        # DRF throttles
│   │   │   └── urls.py             # Все маршруты API
│   │   └── medqueue_project/
│   │       ├── settings.py         # Настройки, CSP, OAuth keys, Celery, Redis
│   │       ├── urls.py             # AuthPageView (Google/FB client id в шаблон)
│   │       └── celery.py           # Celery app + autodiscover
│   ├── html/                       # Фронтенд
│   │   ├── main.html               # Главная + карта
│   │   ├── auth.html               # Вход / регистрация / Google OAuth
│   │   ├── hospital.html           # Карточка больницы
│   │   ├── recording.html          # Запись на приём
│   │   ├── profile.html            # Личный кабинет
│   │   ├── doctor.html             # Портал врача
│   │   └── admin-panel.html        # Панель администратора
│   ├── nginx/
│   │   └── default.conf            # SSL, security headers, proxy
│   ├── css/
│   └── js/
```

---

## Запуск (Production)

```bash
# Клонировать и настроить
git clone <repo>
cd medqueue/startup
cp backend/.env.example backend/.env
# Заполнить .env: SECRET_KEY, GOOGLE_CLIENT_ID, TURNSTILE_SECRET_KEY, ...

# Собрать и запустить
docker-compose build
docker-compose up -d

# Статус
docker ps
# medqueue-backend  Up
# medqueue-worker   Up  (Celery concurrency=4)
# medqueue-nginx    Up  (80, 443)
# medqueue-redis    Up
# medqueue-db       Up
```

## Запуск (локально)

```bash
cd startup/backend
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
# → http://127.0.0.1:8000
```

---

## Переменные окружения (`.env`)

```env
SECRET_KEY=your-django-secret-key
DEBUG=False
ALLOWED_HOSTS=medqueue.me,www.medqueue.me,localhost

# Database
POSTGRES_HOST=db
POSTGRES_DB=medqueue
POSTGRES_USER=medqueue
POSTGRES_PASSWORD=medqueue

# Redis
CACHE_URL=redis://redis:6379/1

# Google OAuth
GOOGLE_CLIENT_ID=1042138271590-xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxx

# Cloudflare Turnstile
TURNSTILE_SITE_KEY=0x4AAAA...
TURNSTILE_SECRET_KEY=0x4AAAA...

# Email
RESEND_API_KEY=re_xxx
```

---

## Prod окружение

| Компонент | Статус |
|-----------|--------|
| `https://medqueue.me` | ✅ Up, SSL Let's Encrypt |
| Django + Gunicorn (4 workers) | ✅ |
| Celery Worker (concurrency=4) | ✅ |
| Redis 7 | ✅ |
| PostgreSQL 15 | ✅ |
| Nginx (SSL terminator) | ✅ |

---

## Лицензия

© 2026 MedQueue. Все права защищены.

