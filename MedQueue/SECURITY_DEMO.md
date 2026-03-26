# Security Demo Checklist (MedQueue)

Этот документ нужен для демонстрации преподавателю, что в проекте реализована практическая защита, а не только «на словах».

## 1) Что говорить в начале (30 секунд)

- В проекте применены 3 слоя защиты:
  - Защита логики (права, роли, валидации)
  - Защита API (throttling/rate limiting)
  - Защита аккаунтов (брутфорс, хеш паролей, подтверждение email)
- Все проверки показываются живыми запросами и ответами сервера.

---

## 2) Доказательство по пунктам задания

## 2.1 SQL Injection

Что показать:
- В коде используется Django ORM без raw SQL в auth/appointments flow.
- Пример: фильтрация идет через `.filter(...)`, `.get(...)`, `.exclude(...)`.

Файлы:
- `startup/backend/appointments/auth_views.py`
- `startup/backend/appointments/views.py`

Короткая фраза:
- «Мы не строим SQL строками, поэтому классическая SQL-инъекция через `' OR 1=1 --` не срабатывает как SQL-команда».

---

## 2.2 Проверка аутентификации и прав

Что показать:
- По умолчанию API требует авторизацию.
- Публичные маршруты отмечены явно.
- Изменение комментария к записи доступно только владельцу.

Файл:
- `startup/backend/medqueue_project/settings.py` (DEFAULT_PERMISSION_CLASSES)
- `startup/backend/appointments/views.py` (`update_comment`)

Живой тест:
1. Без токена вызвать защищенный endpoint (например `/api/appointments/my_appointments/`) => 401.
2. С токеном другого пользователя попытаться менять чужую запись => 403.

---

## 2.3 Защита от брутфорса

Что показать:
- После серии неудачных логинов включается временная блокировка по логину/IP.

Файл:
- `startup/backend/appointments/security.py`
- `startup/backend/appointments/auth_views.py` (`login_user`)

Живой тест (PowerShell):

```powershell
$body = @{ login = "wrong_user"; password = "wrong_pass"; captcha_token = "test" } | ConvertTo-Json
1..6 | ForEach-Object {
  try {
    Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/auth/login/" -Method Post -ContentType "application/json" -Body $body
  } catch {
    $_.Exception.Response.StatusCode.value__
  }
}
```

Ожидаемо:
- первые попытки: 401
- после лимита: 429 (блокировка)

---

## 2.4 Защита email-бота (ограничение запросов кода)

Что показать:
- Для отправки кодов введены cooldown + лимит по email + лимит по IP.

Файл:
- `startup/backend/appointments/security.py` (`check_email_send_allowed`)
- `startup/backend/appointments/auth_views.py` (`register_user`, `resend_code`, `password_reset_request`)

Живой тест:
- Несколько раз подряд дернуть `auth/resend` или `auth/password-reset` => увидеть 429.

---

## 2.5 Ограничение запросов на сайт (rate limiting)

Что показать:
- Глобальные лимиты + отдельные лимиты для auth и ai endpoints.

Файл:
- `startup/backend/appointments/throttles.py`
- `startup/backend/medqueue_project/settings.py` (`DEFAULT_THROTTLE_*`)

Живой тест:
- Часто вызывать `auth/login` или `ai/chat` за короткий интервал => 429.

---

## 2.6 Хеширование пароля (админ не видит пароль)

Что показать:
- Пароли пишутся через `create_user` / `set_password`.
- В базе у пользователя хранится только hash (например `pbkdf2_sha256$...`).

Файл:
- `startup/backend/appointments/auth_views.py`

Живой тест (Django shell):

```powershell
cd startup/backend
.\.venv\Scripts\python.exe manage.py shell -c "from django.contrib.auth.models import User; u=User.objects.exclude(password='').first(); print(u.username, u.password[:25])"
```

Ожидаемо:
- строка начинается с алгоритма хеша (`pbkdf2_sha256$...`), а не с реального пароля.

---

## 3) Что показать в коде за 2 минуты (самое важное)

1. `startup/backend/medqueue_project/settings.py`
- `DEFAULT_PERMISSION_CLASSES`
- `DEFAULT_THROTTLE_CLASSES`
- `DEFAULT_THROTTLE_RATES`

2. `startup/backend/appointments/security.py`
- логика lockout и антифлуда email

3. `startup/backend/appointments/auth_views.py`
- login lock check
- password hashing через `set_password` / `create_user`

---

## 4) Финальная фраза для преподавателя

- «Безопасность проверена не только ревью кода, но и живыми негативными сценариями: неавторизованный доступ, брутфорс, флуд email-кодов и превышение rate-limit. Во всех случаях сервер отдает ожидаемые защитные статусы 401/403/429, а пароль хранится только в хеше».
