# Changelog

## [0.2.0] — 2026-02-27

### Backend

#### Добавлено
- **JWT-аутентификация** (`djangorestframework-simplejwt==5.3.1`)
  - `POST /api/auth/login/` теперь возвращает `access` и `refresh` токены
  - `POST /api/auth/verify/` (подтверждение email) тоже возвращает токены — пользователь сразу авторизован после регистрации
  - `POST /api/auth/token/refresh/` — обновление access-токена по refresh
- **Модель `VerificationCode`** — коды подтверждения email теперь хранятся в БД вместо памяти процесса (`verification_codes = {}`)
  - Поля: `email`, `code`, `name`, `password`, `created_at`
  - Метод `is_expired()` — код истекает через 10 минут
- **Поле `user`** в модели `Appointment` — запись теперь привязывается к авторизованному пользователю (nullable FK)
- **`GET /api/appointments/my_appointments/`** — возвращает записи текущего авторизованного пользователя (требует JWT-токен)
- **`.env.example`** — шаблон переменных окружения (`SECRET_KEY`, email, reCAPTCHA)
- **`VerificationCode`** добавлен в Django Admin

#### Изменено
- `POST /api/appointments/cancel/` — после отмены записи автоматически пересчитываются `queue_position` у всех оставшихся в очереди на тот же день
- `SECRET_KEY` вынесен в `.env` (больше не хардкодится в `settings.py`)
- `REST_FRAMEWORK` в `settings.py` — добавлена `DEFAULT_AUTHENTICATION_CLASSES` с JWT
- `resend_code` — при повторной отправке старый код удаляется из БД, создаётся новый

#### Исправлено
- Коды верификации больше не теряются при перезапуске сервера
- `my_appointments` раньше возвращал все подтверждённые записи всех пользователей — теперь только текущего

### Git / Инфраструктура

#### Добавлено
- `djangorestframework-simplejwt==5.3.1` в `requirements.txt`
- `.env` добавлен в `.gitignore` — секреты больше не попадают в репозиторий
- `db.sqlite3` добавлен в `.gitignore`
- `__pycache__/` и `*.pyc` убраны из git-отслеживания

#### Удалено
- Все `__pycache__/` и `.pyc` файлы из репозитория
- `db.sqlite3` из репозитория
- `__MACOSX/` из репозитория

---

## [0.1.0] — 2026-02-27

### Первоначальная версия

#### Backend
- Модели `Hospital` и `Appointment`
- API: список больниц, создание записи, проверка статуса по коду, отмена записи
- Регистрация с подтверждением email (Yandex SMTP)
- Вход по email/password
- Google reCAPTCHA при регистрации и входе
- Django Admin для больниц и записей

#### Frontend
- Страницы: `main.html`, `recording.html`, `status.html`, `profile.html`, `auth.html`, `contacts and about.html`
- Тёмная/светлая тема
- Мобильное меню
- Навигация с активным состоянием на каждой странице
