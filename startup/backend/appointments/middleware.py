import json
import logging
from django.http import JsonResponse
from rest_framework_simplejwt.authentication import JWTAuthentication

logger = logging.getLogger(__name__)

class PasswordValidationMiddleware:
    """
    Middleware to validate password strength for registration and password changes.
    Returns HTTP 422 Unprocessable Entity if password is weak.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # We target registration and password reset confirmation endpoints
        if request.method == 'POST' and (
            '/auth/register/' in request.path or 
            '/auth/password-reset/confirm/' in request.path
        ):
            try:
                if request.content_type == 'application/json':
                    data = json.loads(request.body)
                    # Extract password fields
                    password = data.get('password') or data.get('new_password') or data.get('new_pass')
                    if password:
                        errors = []
                        if len(password) < 8:
                            errors.append("Пароль должен содержать не менее 8 символов.")
                        if not any(char.isdigit() for char in password):
                            errors.append("Пароль должен содержать как минимум одну цифру.")
                        
                        if errors:
                            return JsonResponse(
                                {"error": " ".join(errors)},
                                status=422
                            )
            except Exception as e:
                # If JSON parsing fails, let the view handle/report bad format
                logger.debug("PasswordValidationMiddleware JSON parse failed: %s", e)
                pass

        return self.get_response(request)


class AdminRBACMiddleware:
    """
    Role-Based Access Control Middleware.
    Restricts access to '/admin/*' and '/api/admin/*' to only users with 'admin' role or staff permissions.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/api/admin/') or request.path.startswith('/admin/'):
            user = request.user
            
            # Since DRF auth runs during dispatch, request.user might not be filled yet
            # for Bearer tokens. We authenticate manually using SimpleJWT.
            if not (user and user.is_authenticated):
                try:
                    authenticator = JWTAuthentication()
                    auth_result = authenticator.authenticate(request)
                    if auth_result:
                        user, _ = auth_result
                        request.user = user
                except Exception as e:
                    logger.debug("AdminRBACMiddleware auth failed: %s", e)
                    pass

            if not (user and user.is_authenticated):
                return JsonResponse({'error': 'Требуется авторизация'}, status=401)

            # Check if user is admin
            is_admin = False
            if user.is_staff or user.is_superuser:
                is_admin = True
            else:
                try:
                    is_admin = (user.profile.role.lower() == 'admin')
                except Exception:
                    pass

            if not is_admin:
                return JsonResponse({'error': 'Доступ запрещен: требуется роль ADMIN'}, status=403)

        return self.get_response(request)


class SecurityHeadersMiddleware:
    """
    Injects standard security headers into all HTTP responses
    to score high on security scans (like securityheaders.com).
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        response['Content-Security-Policy'] = (
            "default-src 'self' https:; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://challenges.cloudflare.com https://unpkg.com; "
            "frame-src 'self' https://challenges.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:;"
        )
        response['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=(), interest-cohort=()'
        return response
