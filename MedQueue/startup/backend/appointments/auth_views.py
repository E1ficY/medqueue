from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
import json
import os
import random
import string
import urllib.parse
import urllib.request

from .models import VerificationCode, DoctorInviteCode, UserProfile, PasswordResetCode


def get_tokens_for_user(user):
    """Генерирует JWT access и refresh токены для пользователя"""
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


def verify_recaptcha_token(token, remote_ip=None):
    """Server-side Google reCAPTCHA verification."""
    if not token:
        return False

    secret_key = os.getenv('RECAPTCHA_SECRET_KEY', '6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe')
    payload = {
        'secret': secret_key,
        'response': token,
    }
    if remote_ip:
        payload['remoteip'] = remote_ip

    data = urllib.parse.urlencode(payload).encode('utf-8')

    try:
        request = urllib.request.Request(
            url='https://www.google.com/recaptcha/api/siteverify',
            data=data,
            method='POST',
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))
            return bool(result.get('success'))
    except Exception:
        return False


@api_view(['POST'])
def validate_doctor_code(request):
    """Проверяет правильность кода врача перед отправкой формы"""
    code = (request.data.get('code') or '').strip().upper()
    if not code:
        return Response({'valid': False, 'error': 'Введите код'})
    invite = DoctorInviteCode.objects.filter(code=code, is_used=False).first()
    if not invite:
        return Response({'valid': False, 'error': 'Код недействителен или уже использован'})
    return Response({
        'valid': True,
        'hospital': invite.hospital.name if invite.hospital else None,
        'specialty': invite.specialty or None,
    })


@api_view(['POST'])
def register_user(request):
    """Регистрация пользователя"""
    name         = request.data.get('name')
    email        = request.data.get('email')
    password     = request.data.get('password')
    username     = (request.data.get('username') or '').strip()
    captcha_token = request.data.get('captcha_token')
    role         = request.data.get('role', 'patient')  # 'patient' | 'doctor'
    doctor_code  = (request.data.get('doctor_code') or '').strip().upper()

    if not verify_recaptcha_token(captcha_token, request.META.get('REMOTE_ADDR')):
        return Response(
            {'error': 'Проверка CAPTCHA не пройдена'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if not all([name, email, password, username]):
        return Response(
            {'error': 'Все поля обязательны (включая логин)'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Валидация логина
    import re
    if not re.match(r'^[a-zA-Z0-9_]{3,30}$', username):
        return Response(
            {'error': 'Логин: от 3 до 30 символов, только латинские буквы, цифры и _'},
            status=status.HTTP_400_BAD_REQUEST
        )
    if User.objects.filter(username=username).exists():
        return Response(
            {'error': 'Логин уже занят'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Для врачей валидируем код приглашения
    if role == 'doctor':
        if not doctor_code:
            return Response(
                {'error': 'Для регистрации врача необходим код приглашения'},
                status=status.HTTP_400_BAD_REQUEST
            )
        invite = DoctorInviteCode.objects.filter(code=doctor_code, is_used=False).first()
        if not invite:
            return Response(
                {'error': 'Недействительный или уже использованный код врача'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    if User.objects.filter(email=email).exists():
        return Response(
            {'error': 'Email уже зарегистрирован'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Удаляем старые коды для этого email и создаём новый
    VerificationCode.objects.filter(email=email).delete()
    code = ''.join(random.choices(string.digits, k=6))
    VerificationCode.objects.create(
        email=email, code=code, name=name, username=username,
        password=password, role=role, doctor_code=doctor_code,
    )
    
    from_email = settings.EMAIL_HOST_USER
    if not from_email:
        return Response(
            {'error': 'Email-сервис не настроен. Заполните EMAIL_HOST_USER и EMAIL_HOST_PASSWORD в файле .env и перезапустите сервер.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    try:
        send_mail(
            subject='Код подтверждения MedQueue',
            message=f'Ваш код подтверждения: {code}\n\nКод действителен в течение 10 минут.\n\nЕсли вы не регистрировались — просто проигнорируйте это письмо.',
            from_email=from_email,
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        return Response(
            {'error': f'Не удалось отправить письмо: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    return Response({'message': f'Код отправлен на {email}'})


@api_view(['POST'])
def verify_email(request):
    """Подтверждение email"""
    email = request.data.get('email')
    code = request.data.get('code')
    
    if not all([email, code]):
        return Response(
            {'error': 'Email и код обязательны'},
            status=status.HTTP_400_BAD_REQUEST
        )

    verification = VerificationCode.objects.filter(email=email).order_by('-created_at').first()

    if not verification:
        return Response(
            {'error': 'Код не найден. Запросите новый.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if verification.is_expired():
        verification.delete()
        return Response(
            {'error': 'Код истёк. Запросите новый.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if verification.code != code:
        return Response(
            {'error': 'Неверный код'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        actual_username = verification.username or email
        # Защита от гонок: проверить ещё раз
        if User.objects.filter(username=actual_username).exists():
            return Response(
                {'error': 'Логин уже занят. Попробуйте другой.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        user = User.objects.create_user(
            username=actual_username,
            email=email,
            password=verification.password,
            first_name=verification.name
        )

        # Создаём UserProfile с ролью
        UserProfile.objects.create(user=user, role=verification.role)

        # Если врач — помечаем код приглашения как использованный
        if verification.role == 'doctor' and verification.doctor_code:
            DoctorInviteCode.objects.filter(
                code=verification.doctor_code, is_used=False
            ).update(is_used=True, used_by=user)

        verification.delete()
        tokens = get_tokens_for_user(user)

        return Response({
            'message': 'Регистрация успешна!',
            'user': {
                'id': user.id,
                'name': user.first_name,
                'email': user.email,
                'username': user.username,
                'role': verification.role,
            },
            **tokens
        })
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def login_user(request):
    """Вход — принимает логин (username или email) + пароль"""
    # Поддерживаем поля 'login' (новое) и 'email' (обратная совместимость)
    login_id = (request.data.get('login') or request.data.get('email') or '').strip()
    password = request.data.get('password')
    captcha_token = request.data.get('captcha_token')

    if not verify_recaptcha_token(captcha_token, request.META.get('REMOTE_ADDR')):
        return Response(
            {'error': 'Проверка CAPTCHA не пройдена'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if not all([login_id, password]):
        return Response(
            {'error': 'Логин и пароль обязательны'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Сначала пробуем как username напрямую
    user = authenticate(username=login_id, password=password)

    # Если не вышло — ищем по email
    if user is None:
        try:
            found = User.objects.get(email__iexact=login_id)
            user = authenticate(username=found.username, password=password)
        except User.DoesNotExist:
            pass
    
    if user is None:
        return Response(
            {'error': 'Неверный логин или пароль'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    tokens = get_tokens_for_user(user)

    # Получаем роль из UserProfile (patient по умолчанию)
    try:
        role = user.profile.role
    except Exception:
        role = 'patient'

    return Response({
        'message': 'Успешно',
        'user': {
            'id': user.id,
            'name': user.first_name or user.username,
            'email': user.email,
            'username': user.username,
            'role': role,
        },
        **tokens
    })


@api_view(['POST'])
def resend_code(request):
    """Повторная отправка"""
    email = request.data.get('email')
    
    if not email:
        return Response(
            {'error': 'Email обязателен'},
            status=status.HTTP_400_BAD_REQUEST
        )

    verification = VerificationCode.objects.filter(email=email).order_by('-created_at').first()

    if not verification:
        return Response(
            {'error': 'Email не найден. Начните регистрацию заново.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    old_name = verification.name
    old_password = verification.password
    old_username = verification.username
    old_role = verification.role
    old_doctor_code = verification.doctor_code
    VerificationCode.objects.filter(email=email).delete()
    new_code = ''.join(random.choices(string.digits, k=6))
    VerificationCode.objects.create(
        email=email, code=new_code, name=old_name, password=old_password,
        username=old_username, role=old_role, doctor_code=old_doctor_code,
    )
    
    from_email = settings.EMAIL_HOST_USER
    if not from_email:
        return Response(
            {'error': 'Email-сервис не настроен. Заполните EMAIL_HOST_USER в файле .env и перезапустите сервер.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    try:
        send_mail(
            subject='Код подтверждения MedQueue',
            message=f'Ваш новый код подтверждения: {new_code}\n\nКод действителен в течение 10 минут.',
            from_email=from_email,
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        return Response(
            {'error': f'Не удалось отправить письмо: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    return Response({'message': f'Новый код отправлен на {email}'})


# ==========================================
# СБРОС ПАРОЛЯ
# ==========================================

@api_view(['POST'])
def password_reset_request(request):
    """Шаг 1: пользователь вводит email, ему приходит код сброса пароля"""
    email = (request.data.get('email') or '').strip().lower()
    if not email:
        return Response({'error': 'Email обязателен'}, status=status.HTTP_400_BAD_REQUEST)

    # Не раскрываем, есть ли такой аккаунт (защита от перебора email)
    user = User.objects.filter(email=email).first()
    if not user:
        # Отвечаем одинаково, чтобы не раскрывать существование email
        return Response({'message': f'Если аккаунт существует, код отправлен на {email}'})

    PasswordResetCode.objects.filter(email=email).delete()
    code = ''.join(random.choices(string.digits, k=6))
    PasswordResetCode.objects.create(email=email, code=code)

    from_email = settings.EMAIL_HOST_USER
    if not from_email:
        return Response(
            {'error': 'Email-сервис не настроен'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    try:
        send_mail(
            subject='Сброс пароля MedQueue',
            message='Вы запросили сброс пароля.\nВаш код: ' + code + '\n\nКод действителен 15 минут.\nЕсли вы ничего не запрашивали — просто игнорируйте это письмо.',
            from_email=from_email,
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception as e:
        print(f'[EMAIL ERROR] {e}')
        return Response({'error': f'Не удалось отправить письмо: {e}'}, status=500)

    return Response({'message': f'Код отправлен на {email}'})


@api_view(['POST'])
def password_reset_confirm(request):
    """Шаг 2: подтверждает код и устанавливает новый пароль"""
    email    = (request.data.get('email') or '').strip().lower()
    code     = (request.data.get('code') or '').strip()
    new_pass = (request.data.get('new_password') or '').strip()

    if not all([email, code, new_pass]):
        return Response({'error': 'Все поля обязательны'}, status=400)
    if len(new_pass) < 6:
        return Response({'error': 'Пароль должен быть не менее 6 символов'}, status=400)

    reset = PasswordResetCode.objects.filter(email=email).order_by('-created_at').first()
    if not reset or reset.code != code:
        return Response({'error': 'Неверный или устаревший код'}, status=400)
    if reset.is_expired():
        reset.delete()
        return Response({'error': 'Код истёк. Запросите новый.'}, status=400)

    user = User.objects.filter(email=email).first()
    if not user:
        return Response({'error': 'Пользователь не найден'}, status=400)

    user.set_password(new_pass)
    user.save()
    reset.delete()

    tokens = get_tokens_for_user(user)
    return Response({
        'message': 'Пароль успешно изменён!',
        'user': {'id': user.id, 'name': user.first_name, 'email': user.email},
        **tokens,
    })


# ==========================================
# ИИ АССИСТЕНТ (Kimi-K2 → Gemini → fallback)
# ==========================================

SYSTEM_PROMPT_AI = (
    'Ты — МедAi, дружелюбный ИИ-ассистент медицинского портала MedQueue (г. Алматы). '
    'Помогаешь пациентам: разбираться с записью к врачу, подсказываешь к какому '
    'специалисту обратиться, отвечаешь на общие медицинские вопросы. '
    'Отвечай коротко (2-4 предложения), по-русски, дружелюбно. '
    'Всегда заканчивай советом обратиться к врачу для точного диагноза. '
    'Не ставь диагнозы и не выписывай рецепты.'
)


@api_view(['POST'])
def ai_chat(request):
    """
    POST /api/ai/chat/
    Body: { "message": "...", "history": [{"role":"user","content":"..."}...] }

    Priorities:
      1. Kimi-K2 via HuggingFace Router (HF_TOKEN in .env)
      2. Gemini 1.5 Flash (GEMINI_API_KEY in .env)
      3. Rule-based fallback (always works)

    Get HF_TOKEN free: https://huggingface.co/settings/tokens
    """
    import json as _json

    user_message = (request.data.get('message') or '').strip()
    history      = request.data.get('history', [])

    if not user_message:
        return Response({'error': 'Сообщение пустое'}, status=400)

    HF_TOKEN      = os.getenv('HF_TOKEN', '').strip()
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '').strip()

    # ── 1. Kimi-K2 via HuggingFace Router ──
    if HF_TOKEN:
        try:
            from openai import OpenAI as _OpenAI
            client = _OpenAI(
                base_url='https://router.huggingface.co/v1',
                api_key=HF_TOKEN,
            )
            messages = [{'role': 'system', 'content': SYSTEM_PROMPT_AI}]
            for item in history[-8:]:
                role = item.get('role', 'user')
                if role not in ('user', 'assistant'):
                    role = 'user'
                content = item.get('content') or item.get('text', '')
                if content:
                    messages.append({'role': role, 'content': content})
            messages.append({'role': 'user', 'content': user_message})

            completion = client.chat.completions.create(
                model='moonshotai/Kimi-K2-Instruct-0905',
                messages=messages,
                max_tokens=512,
                temperature=0.7,
            )
            reply = completion.choices[0].message.content
            return Response({'reply': reply, 'model': 'kimi-k2'})
        except Exception as e:
            print(f'[KIMI-K2 ERROR] {e}')
            # fall through to Gemini

    # ── 2. Gemini 1.5 Flash fallback ──
    if GEMINI_API_KEY:
        try:
            contents = [
                {'role': 'user', 'parts': [{'text': SYSTEM_PROMPT_AI}]},
                {'role': 'model', 'parts': [{'text': 'Понял, готов помочь!'}]},
            ]
            for item in history[-8:]:
                role = 'user' if item.get('role') == 'user' else 'model'
                text_val = item.get('content') or item.get('text', '')
                if text_val:
                    contents.append({'role': role, 'parts': [{'text': text_val}]})
            contents.append({'role': 'user', 'parts': [{'text': user_message}]})

            payload = {
                'contents': contents,
                'generationConfig': {'temperature': 0.7, 'maxOutputTokens': 512},
            }
            url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}'
            data = _json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
            with urllib.request.urlopen(req, timeout=20) as resp:
                result = _json.loads(resp.read().decode())
            text = result['candidates'][0]['content']['parts'][0]['text']
            return Response({'reply': text, 'model': 'gemini'})
        except Exception as e:
            print(f'[GEMINI ERROR] {e}')

    # ── 3. Rule-based fallback ──
    return Response(_fallback_ai_response(user_message))


def _fallback_ai_response(message):
    """Rule-based fallback если Gemini API недоступен — покрывает >20 тем"""
    m = message.lower()

    # --- Запись к врачу ---
    if any(w in m for w in ['записаться', 'запись', 'записать', 'попасть на приём', 'записаться к врачу']):
        return {'reply': '📅 Перейдите в раздел «Главная», выберите клинику → «Записаться». Укажите специалиста, дату и время — код записи придёт сразу.'}

    # --- Температура ---
    if any(w in m for w in ['температура', 'жар', 'лихорадка', 'горю', 'высокая темп']):
        return {'reply': '🌡️ При температуре выше 38.5°C обратитесь к терапевту или вызовите скорую (103). До снижения — пейте больше воды, при необходимости примите жаропонижающее (парацетамол). Для точного диагноза обратитесь к врачу.'}

    # --- Головная боль ---
    if any(w in m for w in ['голова', 'головная боль', 'мигрень', 'голова боли']):
        return {'reply': '🧠 Головная боль бывает при усталости, стрессе, давлении или неврологических причинах. Если боль сильная/частая — обратитесь к неврологу. Для точного диагноза обратитесь к врачу.'}

    # --- Живот / ЖКТ ---
    if any(w in m for w in ['живот', 'желудок', 'тошнота', 'рвота', 'понос', 'диарея', 'запор', 'изжога']):
        return {'reply': '🫁 Боли в животе, тошнота или расстройство ЖКТ — повод обратиться к гастроэнтерологу или терапевту. Если боль острая — вызовите скорую (103). Для точного диагноза обратитесь к врачу.'}

    # --- Сердце ---
    if any(w in m for w in ['сердце', 'сердечное', 'давление', 'тахикардия', 'аритмия', 'инфаркт', 'боль в груди']):
        return {'reply': '❤️ При болях в грудной клетке, учащённом сердцебиении или скачках давления — срочно к кардиологу. При острой боли вызовите 103. Для точного диагноза обратитесь к врачу.'}

    # --- Кашель / ОРВИ ---
    if any(w in m for w in ['кашель', 'насморк', 'орви', 'простуда', 'грипп', 'чихаю', 'горло', 'ангина']):
        return {'reply': '🤧 ОРВИ или грипп лечит терапевт. Пейте тёплые жидкости, больше отдыхайте. При высокой температуре и ухудшении — обратитесь к врачу очно. Для точного диагноза обратитесь к врачу.'}

    # --- Спина, суставы ---
    if any(w in m for w in ['спина', 'позвоночник', 'суставы', 'колено', 'поясница', 'шея']):
        return {'reply': '🦴 Боли в спине и суставах — к ортопеду или неврологу. При травме — к хирургу. Для точного диагноза обратитесь к врачу.'}

    # --- Кожа ---
    if any(w in m for w in ['кожа', 'сыпь', 'зуд', 'акне', 'прыщи', 'дерматит', 'аллергия']):
        return {'reply': '🧴 Кожные проблемы (сыпь, зуд, акне) — к дерматологу. Аллергическую реакцию также оценит аллерголог. Для точного диагноза обратитесь к врачу.'}

    # --- Глаза ---
    if any(w in m for w in ['глаза', 'зрение', 'близорукость', 'дальнозоркость', 'линзы', 'очки']):
        return {'reply': '👁️ Проблемы со зрением — к офтальмологу. Плановую проверку зрения рекомендуется проходить раз в год. Для точного диагноза обратитесь к врачу.'}

    # --- Зубы ---
    if any(w in m for w in ['зубы', 'зуб', 'стоматолог', 'десна', 'боль в зубе']):
        return {'reply': '🦷 Зубная боль — к стоматологу как можно скорее. Для снятия боли временно помогает ибупрофен. Для точного диагноза обратитесь к врачу.'}

    # --- Дети ---
    if any(w in m for w in ['ребёнок', 'дети', 'ребенок', 'малыш', 'педиатр']):
        return {'reply': '👶 Здоровье детей — к педиатру. В Алматы есть детские поликлиники и ДГКБ. Для точного диагноза обратитесь к врачу.'}

    # --- Психическое здоровье ---
    if any(w in m for w in ['депрессия', 'тревога', 'психолог', 'психиатр', 'стресс', 'паника', 'бессонница']):
        return {'reply': '🧘 Психологическое состояние важно. Обратитесь к психологу (без рецептов) или психиатру (с медикаментами). В кризисных ситуациях — телефон доверия: 150. Для точного диагноза обратитесь к врачу.'}

    # --- Диабет / эндо ---
    if any(w in m for w in ['диабет', 'сахар', 'инсулин', 'щитовидка', 'гормоны', 'эндокринолог']):
        return {'reply': '🩸 При симптомах диабета или гормональных нарушениях — к эндокринологу. Сдайте кровь на сахар натощак. Для точного диагноза обратитесь к врачу.'}

    # --- Женское здоровье ---
    if any(w in m for w in ['гинеколог', 'женский врач', 'беременность', 'месячные', 'цикл']):
        return {'reply': '🌸 Женское здоровье — к гинекологу. Плановый осмотр раз в год обязателен. Для точного диагноза обратитесь к врачу.'}

    # --- Скорая ---
    if any(w in m for w in ['скорая', '103', 'вызвать врача', 'критическое', 'потерял сознание']):
        return {'reply': '🚑 При критическом состоянии немедленно звоните 103 (скорая помощь). Не ждите и не занимайтесь самолечением!'}

    # --- Больницы Алматы ---
    if any(w in m for w in ['больница', 'поликлиника', 'клиника', 'алматы', 'где лечиться']):
        return {'reply': '🏥 В MedQueue представлены более 40 больниц и поликлиник Алматы. Откройте главную страницу, выберите клинику на карте или в списке и запишитесь онлайн.'}

    # --- Анализы ---
    if any(w in m for w in ['анализы', 'кровь', 'моча', 'узи', 'мрт', 'рентген', 'обследование']):
        return {'reply': '🔬 Для направления на анализы или инструментальную диагностику (УЗИ, МРТ, рентген) обратитесь к терапевту — он выдаст направление. Для точного диагноза обратитесь к врачу.'}

    # --- Поиск специалиста ---
    if any(w in m for w in ['какой врач', 'к какому врачу', 'специалист', 'кому записаться']):
        return {'reply': '🩺 Если не знаете к кому идти — начните с терапевта: он поставит предварительный диагноз и направит к нужному специалисту. Для записи используйте MedQueue.'}

    # --- Приветствие ---
    if any(w in m for w in ['привет', 'здравствуй', 'хеллоу', 'hi', 'hello', 'даров', 'добрый']):
        return {'reply': '👋 Привет! Я МедAi — ваш медицинский ассистент MedQueue. Задайте вопрос о симптомах, специалистах или записи к врачу в Алматы. 😊'}

    # --- Спасибо ---
    if any(w in m for w in ['спасибо', 'благодар', 'thanks', 'thank']):
        return {'reply': '😊 Пожалуйста! Если появятся ещё вопросы — спрашивайте. Берегите своё здоровье!'}

    # --- По умолчанию ---
    return {
        'reply': (
            '🏥 Я МедAi — ассистент медпортала MedQueue (Алматы). '
            'Могу помочь с выбором специалиста, записью к врачу или ответить на вопрос о симптомах. '
            'Уточните свой вопрос, и я постараюсь помочь!'
        )
    }