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

from .models import VerificationCode


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
def register_user(request):
    """Регистрация пользователя"""
    name = request.data.get('name')
    email = request.data.get('email')
    password = request.data.get('password')
    captcha_token = request.data.get('captcha_token')

    if not verify_recaptcha_token(captcha_token, request.META.get('REMOTE_ADDR')):
        return Response(
            {'error': 'Проверка CAPTCHA не пройдена'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if not all([name, email, password]):
        return Response(
            {'error': 'Все поля обязательны'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if User.objects.filter(email=email).exists():
        return Response(
            {'error': 'Email уже зарегистрирован'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Удаляем старые коды для этого email и создаём новый в БД
    VerificationCode.objects.filter(email=email).delete()
    code = ''.join(random.choices(string.digits, k=6))
    VerificationCode.objects.create(email=email, code=code, name=name, password=password)
    
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
        user = User.objects.create_user(
            username=email,
            email=email,
            password=verification.password,
            first_name=verification.name
        )
        verification.delete()
        tokens = get_tokens_for_user(user)

        return Response({
            'message': 'Регистрация успешна!',
            'user': {
                'id': user.id,
                'name': user.first_name,
                'email': user.email,
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
    """Вход"""
    email = request.data.get('email')
    password = request.data.get('password')
    captcha_token = request.data.get('captcha_token')

    if not verify_recaptcha_token(captcha_token, request.META.get('REMOTE_ADDR')):
        return Response(
            {'error': 'Проверка CAPTCHA не пройдена'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if not all([email, password]):
        return Response(
            {'error': 'Email и пароль обязательны'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    user = authenticate(username=email, password=password)
    
    if user is None:
        return Response(
            {'error': 'Неверные данные'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    tokens = get_tokens_for_user(user)

    return Response({
        'message': 'Успешно',
        'user': {
            'id': user.id,
            'name': user.first_name or user.username,
            'email': user.email,
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
    VerificationCode.objects.filter(email=email).delete()
    new_code = ''.join(random.choices(string.digits, k=6))
    VerificationCode.objects.create(email=email, code=new_code, name=old_name, password=old_password)
    
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