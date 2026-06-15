from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from .email_service import send_email
from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
import json
import os
import random
import re
import string
import time
import urllib.parse
import urllib.request
import urllib.error
import logging

from .models import (
    VerificationCode, DoctorInviteCode, UserProfile, PasswordResetCode,
    Doctor, Hospital, SPECIALTIES_CHOICES,
)
from .security import (
    get_client_ip,
    is_login_locked,
    register_login_failure,
    clear_login_failures,
    check_email_send_allowed,
    log_failed_login,
)
from .throttles import (
    AuthLoginThrottle,
    AuthRegisterThrottle,
    AuthVerifyThrottle,
    AuthResendThrottle,
    PasswordResetThrottle,
    AIChatThrottle,
)

logger = logging.getLogger(__name__)


def get_tokens_for_user(user):
    """Генерирует JWT access и refresh токены для пользователя с ролью и ID"""
    refresh = RefreshToken.for_user(user)
    role = get_effective_role(user)
    refresh['role'] = role
    refresh.access_token['role'] = role
    refresh['id'] = user.id
    refresh.access_token['id'] = user.id
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


def normalize_email(value):
    return (value or '').strip().lower()


def get_effective_role(user):
    if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
        return 'admin'
    try:
        return user.profile.role
    except Exception:
        return 'patient'


def get_user_auth_payload(user):
    role = get_effective_role(user)
    plan = 'free'
    from django.utils import timezone
    from appointments.models import UserSubscription
    sub = UserSubscription.objects.filter(user=user, status='active').first()
    if sub:
        plan = sub.plan

    avatar_base64 = ''
    try:
        if hasattr(user, 'profile') and user.profile.avatar_base64:
            avatar_base64 = user.profile.avatar_base64
    except Exception:
        pass

    return {
        'id': user.id,
        'name': user.first_name or user.username,
        'email': user.email,
        'username': user.username,
        'role': role,
        'is_superuser': user.is_superuser,
        'is_staff': user.is_staff,
        'subscription_plan': plan,
        'avatar_base64': avatar_base64,
    }


def verify_recaptcha_token(token, remote_ip=None):
    """Server-side Cloudflare Turnstile verification."""
    if not token:
        return False

    # Reject obvious dummy/test tokens returned by headless or automated environments
    try:
        t = str(token)
        if 'DUMMY' in t.upper() or t.startswith('XXXX.'):
            logger.warning('Rejected dummy Turnstile token from %s', remote_ip)
            return False
    except Exception:
        pass

    secret_key = os.getenv('TURNSTILE_SECRET_KEY', '').strip()
    if not secret_key:
        logger.error('TURNSTILE_SECRET_KEY is not configured on the server')
        return False

    payload = {
        'secret': secret_key,
        'response': token,
    }
    if remote_ip:
        payload['remoteip'] = remote_ip

    data = urllib.parse.urlencode(payload).encode('utf-8')

    try:
        request = urllib.request.Request(
            url='https://challenges.cloudflare.com/turnstile/v0/siteverify',
            data=data,
            method='POST',
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))
            return bool(result.get('success'))
    except Exception:
        return False


@api_view(['POST'])
@permission_classes([AllowAny])
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
@permission_classes([AllowAny])
@throttle_classes([AuthRegisterThrottle])
def register_user(request):
    """Регистрация пользователя"""
    name         = (request.data.get('name') or '').strip()
    email        = normalize_email(request.data.get('email'))
    password     = request.data.get('password')
    username     = (request.data.get('username') or '').strip()
    captcha_token = request.data.get('captcha_token')
    role         = request.data.get('role', 'patient')  # 'patient' | 'doctor'
    doctor_code  = (request.data.get('doctor_code') or '').strip().upper()
    client_ip = get_client_ip(request)

    if not os.getenv('TURNSTILE_SECRET_KEY', '').strip():
        return Response(
            {'error': 'Сервер не настроен: отсутствует TURNSTILE_SECRET_KEY в backend/.env'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    if not verify_recaptcha_token(captcha_token, client_ip):
        return Response(
            {'error': 'Проверка «не робот» не пройдена. Обновите страницу и пройдите проверку снова.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    phone = (request.data.get('phone') or '').strip()

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
    existing_by_email = User.objects.filter(email=email).first()
    if User.objects.filter(username=username).exclude(pk=getattr(existing_by_email, 'pk', None)).exists():
        return Response(
            {'error': 'Логин уже занят'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Проверка сложности пароля Django-валидаторами
    try:
        probe_user = existing_by_email or User(username=username, email=email, first_name=name)
        validate_password(password, user=probe_user)
    except ValidationError as exc:
        return Response(
            {'error': ' '.join(exc.messages)},
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
    
    if existing_by_email and existing_by_email.is_active:
        return Response(
            {'error': 'Email уже зарегистрирован'},
            status=status.HTTP_400_BAD_REQUEST
        )

    allowed, err_msg = check_email_send_allowed('register', email, client_ip)
    if not allowed:
        return Response({'error': err_msg}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    
    # Создаём/обновляем НЕактивный аккаунт: пароль хранится только как хеш в auth_user.
    with transaction.atomic():
        if existing_by_email:
            user = existing_by_email
            user.username = username
            user.first_name = name
            user.is_active = False
            user.set_password(password)
            user.save(update_fields=['username', 'first_name', 'is_active', 'password'])
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=name,
                is_active=False,
            )

        VerificationCode.objects.filter(email=email).delete()
        code = ''.join(random.choices(string.digits, k=6))
        VerificationCode.objects.create(
            email=email,
            code=code,
            name=name,
            username=username,
            password='',
            role=role,
            doctor_code=doctor_code,
            phone=phone,
        )
    
    try:
        send_email(
            to=email,
            subject='Код подтверждения MedQueue',
            text=f'Ваш код подтверждения: {code}\n\nКод действителен в течение 10 минут.\n\nЕсли вы не регистрировались — просто проигнорируйте это письмо.',
        )
    except Exception as e:
        logger.error('[EMAIL ERROR] register: %s', e)
        return Response(
            {'error': f'Не удалось отправить письмо: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    return Response({'message': f'Код отправлен на {email}'}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([AuthVerifyThrottle])
def verify_email(request):
    """Подтверждение email"""
    email = normalize_email(request.data.get('email'))
    code = (request.data.get('code') or '').strip()
    
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
        with transaction.atomic():
            user = User.objects.filter(email=email).first()
            if not user:
                return Response(
                    {'error': 'Пользователь для верификации не найден. Повторите регистрацию.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Защита от гонок: если username уже занят другим пользователем — ошибка.
            actual_username = verification.username or user.username or email
            if not re.match(r'^[a-zA-Z0-9_]{3,30}$', actual_username):
                import uuid
                actual_username = f"user_{uuid.uuid4().hex[:10]}"
            if User.objects.filter(username=actual_username).exclude(pk=user.pk).exists():
                return Response(
                    {'error': 'Логин уже занят. Повторите регистрацию с другим логином.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            user.username = actual_username
            if verification.name:
                user.first_name = verification.name
            user.is_active = True
            user.save(update_fields=['username', 'first_name', 'is_active'])

            # Создаём/обновляем UserProfile с ролью
            profile, _ = UserProfile.objects.get_or_create(user=user, defaults={'role': verification.role or 'patient'})
            profile.role = verification.role or profile.role or 'patient'
            if getattr(verification, 'phone', None):
                profile.phone = verification.phone
                profile.save(update_fields=['role', 'phone'])
            else:
                profile.save(update_fields=['role'])

            # Если врач — помечаем код приглашения как использованный и создаём Doctor-запись
            if verification.role == 'doctor' and verification.doctor_code:
                invite_qs = DoctorInviteCode.objects.filter(code=verification.doctor_code, is_used=False)
                invite_obj = invite_qs.first()
                invite_qs.update(is_used=True, used_by=user)
                # Автоматически создаём запись Doctor чтобы портал врача сразу начал работать
                if invite_obj and invite_obj.hospital and not Doctor.objects.filter(user=user).exists():
                    Doctor.objects.create(
                        user=user,
                        hospital=invite_obj.hospital,
                        specialty=invite_obj.specialty or '',
                        full_name=user.first_name or user.username,
                        is_active=True,
                    )

            verification.delete()
        tokens = get_tokens_for_user(user)

        effective_role = get_effective_role(user)

        return Response({
            'message': 'Регистрация успешна!',
            'user': {
                'id': user.id,
                'name': user.first_name,
                'email': user.email,
                'username': user.username,
                'role': effective_role,
                'is_superuser': user.is_superuser,
                'is_staff': user.is_staff,
            },
            **tokens
        })
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([AuthLoginThrottle])
def login_user(request):
    """Вход — принимает логин (username или email) + пароль"""
    # Поддерживаем поля 'login' (новое) и 'email' (обратная совместимость)
    login_id = (request.data.get('login') or request.data.get('email') or '').strip()
    password = request.data.get('password')
    captcha_token = request.data.get('captcha_token')
    client_ip = get_client_ip(request)

    if is_login_locked(login_id.lower(), client_ip):
        return Response(
            {'error': 'Слишком много неудачных попыток входа. Попробуйте позже.'},
            status=status.HTTP_429_TOO_MANY_REQUESTS
        )

    if not verify_recaptcha_token(captcha_token, client_ip):
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
        register_login_failure(login_id.lower(), client_ip)
        log_failed_login(login_id.lower(), client_ip, request.META.get('HTTP_USER_AGENT'))
        return Response(
            {'error': 'Неверный логин или пароль'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    if not user.is_active:
        register_login_failure(login_id.lower(), client_ip)
        log_failed_login(login_id.lower(), client_ip, request.META.get('HTTP_USER_AGENT'))
        return Response(
            {'error': 'Аккаунт не активирован. Подтвердите email кодом.'},
            status=status.HTTP_403_FORBIDDEN
        )

    clear_login_failures(login_id.lower(), client_ip)
    
    tokens = get_tokens_for_user(user)

    role = get_effective_role(user)

    return Response({
        'message': 'Успешно',
        'user': get_user_auth_payload(user),
        **tokens
    })


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([AuthResendThrottle])
def resend_code(request):
    """Повторная отправка"""
    email = normalize_email(request.data.get('email'))
    client_ip = get_client_ip(request)
    
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

    allowed, err_msg = check_email_send_allowed('resend', email, client_ip)
    if not allowed:
        return Response({'error': err_msg}, status=status.HTTP_429_TOO_MANY_REQUESTS)

    old_name = verification.name
    old_username = verification.username
    old_role = verification.role
    old_doctor_code = verification.doctor_code
    VerificationCode.objects.filter(email=email).delete()
    new_code = ''.join(random.choices(string.digits, k=6))
    VerificationCode.objects.create(
        email=email, code=new_code, name=old_name, password='',
        username=old_username, role=old_role, doctor_code=old_doctor_code,
    )
    
    try:
        send_email(
            to=email,
            subject='Код подтверждения MedQueue',
            text=f'Ваш новый код подтверждения: {new_code}\n\nКод действителен в течение 10 минут.',
        )
    except Exception as e:
        logger.error('[EMAIL ERROR] resend: %s', e)
        return Response(
            {'error': f'Не удалось отправить письмо: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    return Response({'message': f'Новый код отправлен на {email}'})


# ==========================================
# СБРОС ПАРОЛЯ
# ==========================================

@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([PasswordResetThrottle])
def password_reset_request(request):
    """Шаг 1: пользователь вводит email, ему приходит код сброса пароля"""
    email = normalize_email(request.data.get('email'))
    client_ip = get_client_ip(request)
    if not email:
        return Response({'error': 'Email обязателен'}, status=status.HTTP_400_BAD_REQUEST)

    allowed, err_msg = check_email_send_allowed('password_reset', email, client_ip)
    if not allowed:
        return Response({'error': err_msg}, status=status.HTTP_429_TOO_MANY_REQUESTS)

    # Не раскрываем, есть ли такой аккаунт (защита от перебора email)
    user = User.objects.filter(email=email).first()
    if not user:
        # Отвечаем одинаково, чтобы не раскрывать существование email
        return Response({'message': f'Если аккаунт существует, код отправлен на {email}'})

    PasswordResetCode.objects.filter(email=email).delete()
    code = ''.join(random.choices(string.digits, k=6))
    PasswordResetCode.objects.create(email=email, code=code)

    try:
        send_email(
            to=email,
            subject='Сброс пароля MedQueue',
            text='Вы запросили сброс пароля.\nВаш код: ' + code + '\n\nКод действителен 15 минут.\nЕсли вы ничего не запрашивали — просто игнорируйте это письмо.',
        )
    except Exception as e:
        logger.error('[EMAIL ERROR] password_reset: %s', e)
        return Response({'error': f'Не удалось отправить письмо: {e}'}, status=500)

    return Response({'message': f'Код отправлен на {email}'})


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([PasswordResetThrottle])
def password_reset_confirm(request):
    """Шаг 2: подтверждает код и устанавливает новый пароль"""
    email    = normalize_email(request.data.get('email'))
    code     = (request.data.get('code') or '').strip()
    new_pass = (request.data.get('new_password') or '').strip()

    if not all([email, code, new_pass]):
        return Response({'error': 'Все поля обязательны'}, status=400)
    reset = PasswordResetCode.objects.filter(email=email).order_by('-created_at').first()
    if not reset or reset.code != code:
        return Response({'error': 'Неверный или устаревший код'}, status=400)
    if reset.is_expired():
        reset.delete()
        return Response({'error': 'Код истёк. Запросите новый.'}, status=400)

    user = User.objects.filter(email=email).first()
    if not user:
        return Response({'error': 'Пользователь не найден'}, status=400)

    try:
        validate_password(new_pass, user=user)
    except ValidationError as exc:
        return Response({'error': ' '.join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

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
    'Отвечай максимально коротко и понятно (1-3 коротких абзаца). '
    'Пиши естественно, без шаблонов "Лучший вариант" и "Альтернатива". '
    'Если нужно, предложи 1-2 врача в спокойной разговорной форме. '
    'Всегда заканчивай советом обратиться к врачу для точного диагноза. '
    'Не ставь диагнозы и не выписывай рецепты.'
)

# Simple in-process circuit breaker to avoid hammering failed providers.
_AI_PROVIDER_BLOCK_UNTIL = {
    'kimi': 0.0,
    'gemini': 0.0,
}


def _provider_available(name: str) -> bool:
    return time.time() >= _AI_PROVIDER_BLOCK_UNTIL.get(name, 0.0)


def _block_provider(name: str, seconds: int):
    _AI_PROVIDER_BLOCK_UNTIL[name] = time.time() + max(30, int(seconds))


SYMPTOM_SPECIALTY_RULES = [
    (['температура', 'кашель', 'простуда', 'орви', 'грипп', 'горло', 'слабость'], 'Терапевт'),
    (['операция', 'рана', 'ушиб', 'перелом', 'хирург'], 'Хирург'),
    (['сердце', 'давление', 'тахикардия', 'аритмия', 'боль в груди'], 'Кардиолог'),
    (['голова', 'мигрень', 'головокружение', 'онемение', 'судороги'], 'Невролог'),
    (['кожа', 'сыпь', 'зуд', 'прыщи', 'акне'], 'Дерматолог'),
    (['глаза', 'зрение', 'покраснение глаз'], 'Офтальмолог'),
    (['сахар', 'диабет', 'гормоны', 'щитовидка'], 'Эндокринолог'),
    (['беременность', 'цикл', 'гинеколог'], 'Гинеколог'),
    (['почки', 'моче', 'уролог'], 'Уролог'),
    (['дети', 'ребенок', 'ребёнок', 'малыш', 'педиатр'], 'Педиатр'),
    (['зуб', 'десна', 'стоматолог'], 'Стоматолог'),
    (['тревога', 'депрессия', 'паника', 'психиатр'], 'Психиатр'),
]


RECOMMENDATION_INTENT_KEYWORDS = [
    'порекомендуй', 'посоветуй', 'какой врач', 'к какому врачу',
    'куда обратиться', 'подбери врача', 'нужен врач',
    'какая больница', 'подбери больницу', 'где лечиться',
]


ALL_DOCTORS_INTENT_KEYWORDS = [
    'все врачи', 'всех врачей', 'покажи всех врачей', 'покажи врачей',
    'список врачей', 'врачи из базы', 'все доктора', 'расскажи о всех врачах',
]


DOCTOR_LOOKUP_INTENT_KEYWORDS = [
    'найди врача', 'найти врача', 'есть врач', 'есть ли врач',
    'проверь врача', 'информация о враче', 'о враче', 'где работает врач',
    'врач по имени',
]


def _detect_specialty_from_text(message):
    """Определяет вероятную специальность по тексту запроса."""
    text = (message or '').lower()

    # Явное упоминание специальности из справочника.
    for specialty, _ in SPECIALTIES_CHOICES:
        if specialty.lower() in text:
            return specialty

    for keywords, specialty in SYMPTOM_SPECIALTY_RULES:
        if any(keyword in text for keyword in keywords):
            return specialty
    return None


def _is_recommendation_intent(message):
    text = (message or '').lower()
    if any(keyword in text for keyword in RECOMMENDATION_INTENT_KEYWORDS):
        return True
    return _detect_specialty_from_text(text) is not None


def _is_all_doctors_intent(message):
    text = (message or '').lower()
    if any(keyword in text for keyword in ALL_DOCTORS_INTENT_KEYWORDS):
        return True

    specialty = _detect_specialty_from_text(text)
    if specialty and ('все' in text or 'покажи' in text or 'список' in text):
        return True

    return ('все' in text and ('врачи' in text or 'доктора' in text))


def _is_doctor_lookup_intent(message):
    """Определяет, что пользователь явно ищет конкретного врача по ФИО."""
    text = (message or '').lower().strip()
    if any(keyword in text for keyword in DOCTOR_LOOKUP_INTENT_KEYWORDS):
        return True

    # Эвристика: если есть слово "врач" + минимум 2 похожих на имя токена.
    if 'врач' not in text and 'доктор' not in text:
        return False

    tokens = [
        token for token in re.findall(r"[a-zA-Zа-яА-ЯёЁ]+", text)
        if len(token) >= 3 and token not in {
            'врач', 'доктор', 'клиника', 'больница', 'найди', 'найти', 'покажи',
            'есть', 'ли', 'где', 'какой', 'какая', 'какие', 'работает',
            'хирург', 'терапевт', 'стоматолог', 'кардиолог', 'невролог',
        }
    ]
    return len(tokens) >= 2


def _all_doctors_response(message):
    """Возвращает список всех активных врачей из БД (опционально по специальности)."""
    specialty = _detect_specialty_from_text(message)
    qs = Doctor.objects.filter(is_active=True, hospital__is_active=True).select_related('hospital')
    if specialty:
        qs = qs.filter(specialty=specialty)

    doctors = list(qs.order_by('specialty', 'full_name'))
    if not doctors:
        return {'reply': 'Сейчас в базе нет подходящих врачей.'}

    if specialty:
        lines = [f"В базе найдено врачей по специальности {specialty}: {len(doctors)}."]
    else:
        lines = [f"В базе найдено врачей: {len(doctors)}."]
    for doc in doctors:
        phone = doc.hospital.phone or 'телефон не указан'
        lines.append(
            f"- {doc.full_name} ({doc.specialty}) — {doc.hospital.name}, тел: {phone}"
        )
    return {'reply': '\n'.join(lines)}


def _lookup_doctors_by_name(message):
    """Ищет врачей по имени/фрагментам ФИО по всей БД (включая неактивных)."""
    text = (message or '').lower().strip()
    if not text:
        return []

    tokens = [
        token for token in re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]+", text)
        if len(token) >= 3 and token not in {
            'врач', 'доктор', 'клиника', 'больница', 'найди', 'покажи',
            'есть', 'ли', 'где', 'какой', 'какая', 'какие', 'работает',
            'все', 'врачи', 'доктора', 'всех', 'расскажи', 'обо', 'всех',
        }
    ]
    if not tokens:
        return []

    doctors = Doctor.objects.select_related('hospital').all()
    scored = []

    for doc in doctors:
        name = (doc.full_name or '').lower()
        score = 0
        for token in tokens:
            if token in name:
                score += 3
        if len(tokens) >= 2 and all(token in name for token in tokens[:2]):
            score += 2
        if score > 0:
            scored.append((score, doc))

    scored.sort(key=lambda item: (-item[0], 0 if item[1].is_active else 1, item[1].full_name.lower()))
    return [doc for _, doc in scored[:5]]


def _doctor_lookup_response(message):
    """Формирует короткий ответ по поиску врача по ФИО."""
    matches = _lookup_doctors_by_name(message)
    if not matches:
        return None

    top = matches[0]
    status_hint = '' if top.is_active else ' (сейчас неактивен в системе)'
    phone = top.hospital.phone or 'телефон не указан'

    reply = (
        f"Нашел врача в базе: {top.full_name} ({top.specialty}){status_hint}. "
        f"Клиника: {top.hospital.name}, тел: {phone}."
    )

    if len(matches) > 1:
        alt = matches[1]
        alt_phone = alt.hospital.phone or 'телефон не указан'
        reply += f" Еще вариант: {alt.full_name} ({alt.specialty}), {alt.hospital.name}, тел: {alt_phone}."

    return {'reply': reply}


def _get_ai_recommendation_data(message):
    """Возвращает релевантных врачей/больницы из БД для ИИ-ответа."""
    specialty = _detect_specialty_from_text(message)

    doctors_base_qs = Doctor.objects.filter(
        is_active=True,
        hospital__is_active=True,
    ).select_related('hospital')

    doctors_qs = doctors_base_qs
    if specialty:
        doctors_qs = doctors_qs.filter(specialty=specialty)
        # Если по специальности никого нет — не теряем врачей, показываем лучшие доступные варианты.
        if not doctors_qs.exists():
            doctors_qs = doctors_base_qs

    doctors = list(doctors_qs)
    doctors.sort(
        key=lambda doc: (
            -float(doc.avg_rating or 0),
            -(doc.reviews_count or 0),
            doc.hospital.waiting_time,
            doc.full_name.lower(),
        )
    )
    doctors = doctors[:6]

    hospitals_qs = Hospital.objects.filter(is_active=True)
    if doctors:
        hospital_ids = [doc.hospital_id for doc in doctors]
        hospitals_qs = hospitals_qs.filter(id__in=hospital_ids)
    hospitals = list(hospitals_qs.order_by('waiting_time', 'name')[:3])

    return {
        'specialty': specialty,
        'doctors': doctors,
        'hospitals': hospitals,
    }


def _build_ai_db_context(message):
    """Формирует текстовый контекст для внешней LLM на основе БД MedQueue."""
    data = _get_ai_recommendation_data(message)
    doctors = data['doctors']
    hospitals = data['hospitals']

    if not doctors and not hospitals:
        return 'В базе сейчас нет подходящих активных врачей/больниц. Дай общий совет и предложи уточнить симптомы.'

    context_lines = []
    if data['specialty']:
        context_lines.append(f"Определи запрос как направление к специалисту: {data['specialty']}.")

    if doctors:
        context_lines.append('Доступные врачи из БД:')
        for doc in doctors:
            phone = doc.hospital.phone or 'телефон не указан'
            context_lines.append(
                f"- {doc.full_name} ({doc.specialty}), рейтинг: {doc.avg_rating}/5 ({doc.reviews_count} отзывов), "
                f"{doc.hospital.name}, адрес: {doc.hospital.address}, тел: {phone}"
            )

    if hospitals:
        context_lines.append('Доступные больницы из БД:')
        for hospital in hospitals:
            phone = hospital.phone or 'телефон не указан'
            context_lines.append(
                f"- {hospital.name}, адрес: {hospital.address}, среднее ожидание: {hospital.waiting_time} мин, тел: {phone}"
            )

    context_lines.append('Если пользователь просит рекомендацию, обязательно выдели 1 лучшего врача и добавь 1-2 альтернативы.')
    return '\n'.join(context_lines)


def _fallback_db_recommendation_response(message):
    """Rule-based ответ с конкретными врачами/больницами из БД в разговорном формате."""
    data = _get_ai_recommendation_data(message)
    doctors = data['doctors']
    hospitals = data['hospitals']

    if not doctors and not hospitals:
        return None

    specialty_hint = data['specialty']
    top_doctor = doctors[0] if doctors else None

    if top_doctor:
        phone = top_doctor.hospital.phone or 'телефон не указан'
        lines = []

        if specialty_hint:
            lines.append(f"По вашему описанию лучше начать с {specialty_hint.lower()}.")
        else:
            lines.append('По вашему запросу вот самый подходящий вариант:')

        lines.append(
            f"Основная рекомендация: {top_doctor.full_name} ({top_doctor.specialty}), "
            f"{top_doctor.hospital.name}, рейтинг {top_doctor.avg_rating}/5, тел. {phone}."
        )

        alternatives = doctors[1:3]
        if alternatives:
            alt_parts = []
            for doc in alternatives:
                alt_phone = doc.hospital.phone or 'телефон не указан'
                alt_parts.append(
                    f"{doc.full_name} ({doc.specialty}), {doc.hospital.name}, рейтинг {doc.avg_rating}/5, тел. {alt_phone}"
                )
            lines.append('Альтернативы: ' + '; '.join(alt_parts) + '.')

        lines.append('Если симптомы усиливаются или держатся больше 2-3 дней, лучше записаться на очный прием.')
        return {'reply': ' '.join(lines)}

    if hospitals:
        first = hospitals[0]
        first_phone = first.phone or 'телефон не указан'
        lines = [
            f"Можно начать с {first.name} ({first.address}, тел. {first_phone})."
        ]

        rest = hospitals[1:3]
        if rest:
            options = []
            for h in rest:
                phone = h.phone or 'телефон не указан'
                options.append(f"{h.name} ({h.address}, тел. {phone})")
            lines.append('Еще варианты: ' + '; '.join(options) + '.')

        lines.append('Выберите клинику по удобному адресу и ближайшему времени приема.')
        return {'reply': ' '.join(lines)}

    return None


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([AIChatThrottle])
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

    # Запросы вида "покажи всех врачей" — возвращаем полный список из БД.
    if _is_all_doctors_intent(user_message):
        all_docs = _all_doctors_response(user_message)
        return Response({**all_docs, 'model': 'medqueue-db-all'})

    # Точный/приближенный поиск врача по ФИО — только при явном намерении пользователя.
    if _is_doctor_lookup_intent(user_message):
        doctor_lookup = _doctor_lookup_response(user_message)
        if doctor_lookup:
            return Response({**doctor_lookup, 'model': 'medqueue-db-name'})

    HF_TOKEN      = os.getenv('HF_TOKEN', '').strip()
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '').strip()
    db_context = _build_ai_db_context(user_message)
    runtime_system_prompt = f"{SYSTEM_PROMPT_AI}\n\nКонтекст MedQueue из БД:\n{db_context}"

    # ── 1. Kimi-K2 via HuggingFace Router ──
    if HF_TOKEN and _provider_available('kimi'):
        try:
            from openai import OpenAI as _OpenAI
            client = _OpenAI(
                base_url='https://router.huggingface.co/v1',
                api_key=HF_TOKEN,
            )
            messages = [{'role': 'system', 'content': runtime_system_prompt}]
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
            err = str(e)
            # 402 / credits exhausted -> block for 1 hour.
            if '402' in err or 'depleted your monthly included credits' in err.lower():
                _block_provider('kimi', 3600)
                print('[KIMI-K2 ERROR] credits exhausted, provider blocked for 60m')
            else:
                # Transient unknown error -> block shortly.
                _block_provider('kimi', 300)
                print(f'[KIMI-K2 ERROR] temporary failure, blocked for 5m: {err}')
            # fall through to Gemini

    # ── 2. Gemini 1.5 Flash fallback ──
    if GEMINI_API_KEY and _provider_available('gemini'):
        try:
            contents = [
                {'role': 'user', 'parts': [{'text': runtime_system_prompt}]},
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
        except urllib.error.HTTPError as e:
            body = ''
            try:
                body = e.read().decode('utf-8', errors='ignore')
            except Exception:
                pass
            # 400 usually key/config/request problem -> longer block.
            if e.code == 400:
                _block_provider('gemini', 1800)
                print(f'[GEMINI ERROR] bad request, provider blocked for 30m: {body[:180]}')
            else:
                _block_provider('gemini', 300)
                print(f'[GEMINI ERROR] HTTP {e.code}, blocked for 5m')
        except Exception as e:
            _block_provider('gemini', 300)
            print(f'[GEMINI ERROR] temporary failure, blocked for 5m: {e}')

    # ── 3. Local fallback ──
    local_reply = _fallback_ai_response(user_message)
    return Response({**local_reply, 'model': 'medqueue-local'})


def _fallback_ai_response(message):
    """Локальный ответ по смыслу запроса без жестких шаблонов."""
    text = (message or '').strip()
    lower = text.lower()

    if _is_all_doctors_intent(text):
        return _all_doctors_response(text)

    if _is_doctor_lookup_intent(text):
        direct = _doctor_lookup_response(text)
        if direct:
            return direct

    db_reco = _fallback_db_recommendation_response(text)
    if db_reco:
        return db_reco

    specialty = _detect_specialty_from_text(text)
    asks_medicine = any(x in lower for x in ['что выпить', 'что принять', 'что можно выпить', 'что можно принять'])

    if specialty and asks_medicine:
        advice = {
            'Стоматолог': 'Можно начать с обезболивающего на основе ибупрофена или парацетамола по инструкции, если нет противопоказаний.',
            'Терапевт': 'Можно начать с базовой симптоматической помощи: питье, отдых и жаропонижающее по инструкции при температуре.',
            'Кардиолог': 'При боли в груди или выраженной одышке не начинайте самолечение, лучше сразу обратиться за неотложной помощью.',
        }
        line = advice.get(specialty, 'На первом этапе используйте только безопасную симптоматическую помощь по инструкции к препарату.')
        docs = _get_ai_recommendation_data(text).get('doctors', [])[:2]
        if docs:
            doctors_line = '; '.join([f"{d.full_name} ({d.hospital.name})" for d in docs])
            return {'reply': f"{line} Подходящие врачи: {doctors_line}."}
        return {'reply': line}

    if specialty:
        docs = _get_ai_recommendation_data(text).get('doctors', [])[:2]
        if docs:
            doctors_line = '; '.join([f"{d.full_name} ({d.hospital.name})" for d in docs])
            return {'reply': f"По симптомам логично начать с {specialty.lower()}. Подходящие врачи: {doctors_line}."}
        return {'reply': f"По описанию лучше начать с {specialty.lower()}."}

    if any(x in lower for x in ['болит', 'боль', 'температура', 'кашель', 'тошнит', 'голова']):
        return {'reply': 'Опишите симптомы точнее: что болит, как давно и есть ли температура. Подберу врача и первый шаг.'}

    return {'reply': 'Уточните запрос: врач, специальность, больница или запись на прием.'}


@api_view(['POST'])
@permission_classes([AllowAny])
def google_oauth(request):
    """
    POST /api/auth/google/
    Бэкенд принимает access_token, запрашивает профиль у Google и возвращает JWT.
    """
    access_token = request.data.get('access_token')
    if not access_token:
        return Response({'error': 'access_token обязателен'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        url = 'https://www.googleapis.com/oauth2/v3/userinfo'
        req = urllib.request.Request(
            url,
            headers={'Authorization': f'Bearer {access_token}'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            profile = json.loads(response.read().decode('utf-8'))
    except Exception as e:
        logger.error('[GOOGLE OAuth Error]: %s', e)
        return Response({'error': 'Не удалось проверить токен в Google: ' + str(e)}, status=status.HTTP_400_BAD_REQUEST)

    email = normalize_email(profile.get('email'))
    if not email:
        return Response({'error': 'Google не вернул email'}, status=status.HTTP_400_BAD_REQUEST)

    name = profile.get('name') or profile.get('given_name') or email.split('@')[0]

    with transaction.atomic():
        user = User.objects.filter(email=email).first()
        if not user:
            username = email.split('@')[0]
            # Валидация логина
            import re
            if not re.match(r'^[a-zA-Z0-9_]{3,30}$', username):
                username = f"user_{User.objects.count() + 1}"
            if User.objects.filter(username=username).exists():
                import uuid
                username = f"{username}_{uuid.uuid4().hex[:6]}"
            
            user = User.objects.create_user(
                username=username,
                email=email,
                first_name=name,
                is_active=True
            )
            user.set_password(User.objects.make_random_password(length=24))
            user.save()
        else:
            if not user.is_active:
                user.is_active = True
                user.save(update_fields=['is_active'])

        UserProfile.objects.get_or_create(
            user=user,
            defaults={'role': 'patient'}
        )

    tokens = get_tokens_for_user(user)
    role = get_effective_role(user)

    return Response({
        'message': 'Вход выполнен успешно через Google',
        'user': get_user_auth_payload(user),
        **tokens
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def facebook_oauth(request):
    """
    POST /api/auth/facebook/
    Бэкенд принимает access_token, запрашивает профиль у Facebook Graph API и возвращает JWT.
    """
    access_token = request.data.get('access_token')
    if not access_token:
        return Response({'error': 'access_token обязателен'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        quoted_token = urllib.parse.quote(access_token)
        url = f"https://graph.facebook.com/me?fields=id,name,email&access_token={quoted_token}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            profile = json.loads(response.read().decode('utf-8'))
    except Exception as e:
        logger.error('[FACEBOOK OAuth Error]: %s', e)
        return Response({'error': 'Не удалось проверить токен в Facebook: ' + str(e)}, status=status.HTTP_400_BAD_REQUEST)

    fb_id = profile.get('id')
    if not fb_id:
        return Response({'error': 'Facebook не вернул уникальный идентификатор профиля'}, status=status.HTTP_400_BAD_REQUEST)

    email = normalize_email(profile.get('email'))
    if not email:
        email = f"fb_{fb_id}@facebook.com"

    name = profile.get('name') or email.split('@')[0]

    with transaction.atomic():
        user = User.objects.filter(email=email).first()
        if not user:
            username = f"fb_{fb_id}"
            if User.objects.filter(username=username).exists():
                import uuid
                username = f"{username}_{uuid.uuid4().hex[:6]}"
            
            user = User.objects.create_user(
                username=username,
                email=email,
                first_name=name,
                is_active=True
            )
            user.set_password(User.objects.make_random_password(length=24))
            user.save()
        else:
            if not user.is_active:
                user.is_active = True
                user.save(update_fields=['is_active'])

        UserProfile.objects.get_or_create(
            user=user,
            defaults={'role': 'patient'}
        )

    tokens = get_tokens_for_user(user)
    role = get_effective_role(user)

    return Response({
        'message': 'Вход выполнен успешно через Facebook',
        'user': get_user_auth_payload(user),
        **tokens
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_avatar(request):
    """
    POST /api/auth/avatar/
    Принимает Base64 строку и сохраняет её в профиль пользователя.
    """
    avatar_base64 = request.data.get('avatar_base64')
    if not avatar_base64:
        return Response({'error': 'avatar_base64 обязателен'}, status=status.HTTP_400_BAD_REQUEST)

    # Проверка размера
    if len(avatar_base64) > 2 * 1024 * 1024:
        return Response({'error': 'Слишком большое изображение'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        profile = request.user.profile
        profile.avatar_base64 = avatar_base64
        profile.save(update_fields=['avatar_base64'])
        
        from appointments.auth_views import get_user_auth_payload, get_tokens_for_user
        tokens = get_tokens_for_user(request.user)
        
        return Response({
            'message': 'Аватар обновлен',
            'user': get_user_auth_payload(request.user),
            **tokens
        })
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)