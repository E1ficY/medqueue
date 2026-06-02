from django.core.cache import cache


LOGIN_FAIL_LIMIT = 5
LOGIN_FAIL_WINDOW_SECONDS = 15 * 60
LOGIN_LOCK_SECONDS = 30 * 60

EMAIL_CODE_COOLDOWN_SECONDS = 60
EMAIL_CODE_PER_HOUR_LIMIT = 5
EMAIL_CODE_PER_IP_PER_HOUR_LIMIT = 20


def get_client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '') or 'unknown'


def _cache_incr(key, timeout):
    current = cache.get(key)
    if current is None:
        cache.set(key, 1, timeout=timeout)
        return 1
    try:
        return cache.incr(key)
    except ValueError:
        # Backends that cannot incr non-int values
        value = int(current) + 1
        cache.set(key, value, timeout=timeout)
        return value


def _login_key(prefix, value):
    return f"sec:login:{prefix}:{value}"


def is_login_locked(identifier, ip):
    by_id_locked = cache.get(_login_key('lock:id', identifier))
    by_ip_locked = cache.get(_login_key('lock:ip', ip))
    return bool(by_id_locked or by_ip_locked)


def register_login_failure(identifier, ip):
    id_fails = _cache_incr(_login_key('fails:id', identifier), LOGIN_FAIL_WINDOW_SECONDS)
    ip_fails = _cache_incr(_login_key('fails:ip', ip), LOGIN_FAIL_WINDOW_SECONDS)

    if id_fails >= LOGIN_FAIL_LIMIT:
        cache.set(_login_key('lock:id', identifier), 1, timeout=LOGIN_LOCK_SECONDS)
    if ip_fails >= LOGIN_FAIL_LIMIT:
        cache.set(_login_key('lock:ip', ip), 1, timeout=LOGIN_LOCK_SECONDS)


def clear_login_failures(identifier, ip):
    cache.delete(_login_key('fails:id', identifier))
    cache.delete(_login_key('fails:ip', ip))
    cache.delete(_login_key('lock:id', identifier))
    cache.delete(_login_key('lock:ip', ip))


def check_email_send_allowed(purpose, email, ip):
    # Anti-flood cooldown per email and purpose
    cooldown_key = f"sec:mail:{purpose}:cooldown:{email}"
    if cache.get(cooldown_key):
        return False, 'Слишком часто. Повторите отправку кода через минуту.'

    # Hourly limits per email
    email_hour_key = f"sec:mail:{purpose}:hour:email:{email}"
    email_hour_count = _cache_incr(email_hour_key, 60 * 60)
    if email_hour_count > EMAIL_CODE_PER_HOUR_LIMIT:
        return False, 'Превышен лимит запросов на отправку кода. Попробуйте позже.'

    # Hourly limits per IP
    ip_hour_key = f"sec:mail:{purpose}:hour:ip:{ip}"
    ip_hour_count = _cache_incr(ip_hour_key, 60 * 60)
    if ip_hour_count > EMAIL_CODE_PER_IP_PER_HOUR_LIMIT:
        return False, 'Слишком много запросов с этого IP. Попробуйте позже.'

    cache.set(cooldown_key, 1, timeout=EMAIL_CODE_COOLDOWN_SECONDS)
    return True, None


def log_failed_login(email, ip, user_agent):
    import os
    import json
    from django.utils import timezone
    from django.conf import settings

    log_dir = os.path.join(settings.BASE_DIR, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'security.log')

    log_entry = {
        'timestamp': timezone.now().isoformat(),
        'event': 'FAILED_LOGIN',
        'email': email,
        'ip': ip,
        'user_agent': user_agent or 'unknown'
    }

    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Failed to write security log: %s. Entry: %s", e, log_entry)

