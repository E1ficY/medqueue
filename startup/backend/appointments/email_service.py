"""
email_service.py
================
Единая точка отправки почты для MedQueue.

Логика:
  1. Если задан RESEND_API_KEY — отправляем через Resend HTTP Python SDK
     (HTTP → HTTPS, не нужны открытые SMTP-порты, работает на DigitalOcean).
  2. Иначе — используем стандартный Django send_mail (SMTP).

Импортируй и используй так:
    from appointments.email_service import send_email
    send_email(to='user@example.com', subject='Привет', text='Ваш код: 123456')
"""
import logging
import os

from django.conf import settings
from django.core.mail import send_mail as django_send_mail

logger = logging.getLogger(__name__)


def _send_via_resend(*, to: str, subject: str, text: str) -> None:
    """Отправляет письмо через Resend HTTP Python SDK."""
    try:
        import resend  # pip install resend>=2.0.0
    except ImportError as exc:
        raise RuntimeError(
            "Пакет 'resend' не установлен. Добавьте resend>=2.0.0 в requirements.txt"
        ) from exc

    api_key = getattr(settings, 'RESEND_API_KEY', '') or os.getenv('RESEND_API_KEY', '')
    if not api_key:
        raise RuntimeError('RESEND_API_KEY не задан в .env')

    resend.api_key = api_key

    from_email = (
        getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        or os.getenv('RESEND_FROM_EMAIL', '')
        or 'MedQueue <onboarding@resend.dev>'
    )

    params = resend.Emails.SendParams(
        from_=from_email,
        to=[to],
        subject=subject,
        text=text,
    )
    result = resend.Emails.send(params)
    logger.info('Resend email sent: id=%s to=%s subject=%s', result.get('id'), to, subject)


def _send_via_smtp(*, to: str, subject: str, text: str) -> None:
    """Отправляет письмо через Django SMTP backend."""
    from_email = settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER
    if not from_email:
        raise RuntimeError(
            'Email-сервис не настроен. Заполните EMAIL_HOST_USER или RESEND_API_KEY в .env'
        )
    django_send_mail(
        subject=subject,
        message=text,
        from_email=from_email,
        recipient_list=[to],
        fail_silently=False,
    )
    logger.info('SMTP email sent to=%s subject=%s', to, subject)


def send_email(*, to: str, subject: str, text: str) -> None:
    """
    Основная функция отправки.
    Автоматически выбирает Resend API или SMTP в зависимости от конфигурации.

    Args:
        to:      Адрес получателя.
        subject: Тема письма.
        text:    Текст письма (plain text).

    Raises:
        Exception: Если отправка не удалась (исключение пробрасывается наверх,
                   чтобы вызывающий код мог вернуть 500 пользователю).
    """
    resend_key = getattr(settings, 'RESEND_API_KEY', '') or os.getenv('RESEND_API_KEY', '')

    if resend_key:
        logger.debug('Email backend: Resend HTTP API')
        _send_via_resend(to=to, subject=subject, text=text)
    else:
        logger.debug('Email backend: SMTP')
        _send_via_smtp(to=to, subject=subject, text=text)
