# MedQueue 🏥 — Enterprise Edition (v7.0)

> Система электронной очереди в медицинские учреждения Алматы.
> **v7.0** — Production-ready: Docker, SSL, Prometheus + Grafana, Telegram Alerts, Daily Backups, Nginx Rate Limiting, CI/CD.

🌐 **Live:** https://medqueue.me

---

## 🛠 Стек технологий

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

### Infrastructure & DevOps
| Компонент | Назначение |
|-----------|------------|
| Docker & Compose | Контейнеризация (10 контейнеров) |
| Nginx | SSL-терминатор, Reverse Proxy, Rate Limiting |
| Let's Encrypt | SSL-сертификаты |
| Cloudflare | CDN, DDoS-защита, WAF |
| Prometheus | Сбор метрик и мониторинг |
| Grafana | Визуализация данных |
| Alertmanager | Система оповещений об инцидентах |
| Telegram Bot | Уведомления об алертах и бэкапах |
| GitHub Actions | CI/CD автоматический деплой |

---

## 🔒 Безопасность и Защита

### Многоуровневый Rate Limiting (Nginx)
Реализована эшелонированная защита от брутфорса и DDoS на уровне балансировщика:
- `auth_limit` (`/api/auth/`): **5 запросов/мин** — Защита от перебора паролей
- `api_limit` (`/api/`): **20 запросов/сек** — Защита от парсинга данных
- `general_limit` (`/`): **60 запросов/сек** — Защита от классического DDoS

### Сетевая Изоляция
- **Открыто снаружи (HTTPS):** Backend API, Frontend, Grafana (с авторизацией)
- **Закрыто внутри Docker (Секретно):** Prometheus, Alertmanager, PostgreSQL, Redis, Node-Exporter

### OWASP
- **A01 Broken Access Control:** `filter(user=request.user)` + `_require_admin()` + RBAC middleware
- **A03 Injection:** Использование Django ORM, никаких сырых SQL запросов
- **A07 Auth Failures:** JWT с коротким временем жизни, OTP коды, блокировка по IP

---

## 📈 Мониторинг и Алерты (Observability)

Проект обладает энтерпрайз-стеком мониторинга:
1. **Prometheus** собирает метрики раз в 15 секунд (Django, Node Exporter)
2. **Grafana** (`/grafana/`) отображает RPS, Latency, использование CPU/RAM
3. **Alertmanager** отслеживает 4 критических правила:
   - 🔴 **BackendDown:** Бэкенд не отвечает > 1 минуты
   - 🔴 **HighErrorRate:** >5% ошибок 5xx
   - 🟡 **HighCpuLoad:** Загрузка CPU > 85%
   - 🟡 **LowMemory:** RAM < 10%
4. **Telegram Bot** мгновенно присылает уведомления дежурному инженеру при срабатывании алерта и при его разрешении (✅ РЕШЕНО).

---

## 💾 Автоматические Бэкапы

Каждые 24 часа запускается контейнер `medqueue-backup`:
- Выполняет `pg_dump` базы данных
- Сжимает дамп через `gzip`
- Хранит ровно 7 последних копий (ротация)
- Отправляет детальный отчёт в Telegram (успех/ошибка, размер файла, количество копий)

---

## 👥 Роли пользователей (RBAC)

### 👤 Неавторизованный (гость)
Доступно без токена:
- `GET /api/hospitals/` — список больниц (кэш Redis)
- `GET /api/hospitals/{id}/` — карточка больницы
- `GET /api/hospitals/{id}/doctors/` — врачи по специальностям
- `GET /api/doctors/` — каталог врачей
- `POST /api/auth/register/` — регистрация + CAPTCHA
- `POST /api/auth/login/` — вход → JWT
- `POST /api/auth/google/` — вход через Google
- `POST /api/auth/facebook/` — вход через Facebook

### 🙋 Пациент (`role: patient`)
Всё что доступно гостю +
- `GET /api/appointments/` — **только свои** записи
- `POST /api/appointments/` — создать запись
- `PATCH /api/appointments/{id}/` — изменить **только свою** запись
- `DELETE /api/appointments/{id}/` — отменить **только свою** запись
- `GET /api/profile/` — личный кабинет
- `POST /api/subscription/activate/` — управление подпиской

### 🩺 Врач (`role: doctor`)
Всё что пациент +
- `GET /api/doctor/me/` — свой профиль врача
- `GET /api/doctor/appointments/` — записи к себе
- `PATCH /api/doctor/appointments/{id}/` — изменить статус приёма
- `POST /api/doctor/appointments/{id}/recommendation/` — написать рекомендацию
- `POST /api/doctor/appointments/{id}/prescription/` — выписать рецепт

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

## 🔗 API-эндпоинты

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
| `GET` | `/api/profile/` | Профиль пользователя |
| `GET` | `/api/subscription/me/` | Моя подписка |
| `POST` | `/api/subscription/activate/` | Активировать подписку |

### Врач (JWT + role=doctor)
| Метод | URL | Описание |
|-------|-----|----------|
| `GET` | `/api/doctor/me/` | Профиль врача |
| `GET` | `/api/doctor/appointments/` | Записи к врачу |
| `PATCH` | `/api/doctor/appointments/{id}/` | Изменить статус |
| `POST` | `/api/doctor/appointments/{id}/recommendation/` | Рекомендации |
| `POST` | `/api/doctor/appointments/{id}/prescription/` | Рецепт |

### Администратор (JWT + role=admin)
| Метод | URL | Описание |
|-------|-----|----------|
| `GET` | `/api/admin/stats/` | Статистика |
| `GET/POST` | `/api/admin/hospitals/` | Больницы |
| `GET/POST` | `/api/admin/doctors/` | Врачи |
| `GET/POST` | `/api/admin/invite-codes/` | Коды для врачей |
| `GET` | `/api/admin/users/` | Пользователи |

---

## ⚡ Redis-кэш и Оптимизация

- Кэширование публичных эндпоинтов на 60 секунд (список больниц, врачей). 
- Время ответа из кэша: **~3мс** (вместо ~150мс из БД).
- Заголовок `X-Cache: HIT / MISS` для отладки.
- Отправка email и генерация тяжелых отчетов вынесена в фоновые задачи **Celery**. Время ответа API при регистрации снижено с 3с до мгновенного `200 OK`.

---

## 🚀 Запуск и Развертывание

### CI/CD Pipeline (GitHub Actions)
При push в ветку `main`, GitHub Actions автоматически:
1. Подключается по SSH к DigitalOcean
2. Выполняет `git pull`
3. Запускает `docker-compose up -d --build`

### Ручной запуск (Production)
```bash
git clone <repo>
cd medqueue/startup
# Настроить backend/.env (SECRET_KEY, DB_PASS, TELEGRAM_TOKEN, и т.д.)
docker-compose up -d --build
```

### Локальная разработка
```bash
cd startup/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

---
*© 2026 MedQueue. Система разработана в рамках дипломного/курсового проекта.*
