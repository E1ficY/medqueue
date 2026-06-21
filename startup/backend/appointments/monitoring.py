import logging
from typing import Optional

from django.conf import settings

try:
    from posthog import Posthog
except Exception:  # pragma: no cover
    Posthog = None

logger = logging.getLogger(__name__)
_posthog_client: Optional[object] = None


def _get_posthog_client():
    global _posthog_client
    if _posthog_client is not None:
        return _posthog_client

    api_key = getattr(settings, 'POSTHOG_API_KEY', '')
    host = getattr(settings, 'POSTHOG_HOST', 'https://us.i.posthog.com')
    if not api_key or Posthog is None:
        _posthog_client = False
        return _posthog_client

    try:
        _posthog_client = Posthog(project_api_key=api_key, host=host)
    except Exception as exc:  # pragma: no cover
        logger.warning('PostHog init failed: %s', exc)
        _posthog_client = False
    return _posthog_client


class PostHogMiddleware:
    """Sends lightweight API events to PostHog when configured via env vars."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if not request.path.startswith('/api/'):
            return response

        client = _get_posthog_client()
        if not client:
            return response

        try:
            distinct_id = 'anonymous'
            if getattr(request, 'user', None) and request.user.is_authenticated:
                distinct_id = f'user:{request.user.id}'

            event = 'api.error' if response.status_code >= 500 else 'api.request'
            client.capture(
                distinct_id=distinct_id,
                event=event,
                properties={
                    'path': request.path,
                    'method': request.method,
                    'status_code': response.status_code,
                },
            )
        except Exception as exc:  # pragma: no cover
            logger.warning('PostHog capture failed: %s', exc)

        return response

def track_event(user_id: int, event_name: str, properties: dict = None):
    client = _get_posthog_client()
    if not client:
        return
    try:
        client.capture(
            distinct_id=str(user_id) if user_id else 'anonymous',
            event=event_name,
            properties=properties or {}
        )
    except Exception as exc:
        logger.warning('PostHog capture event failed: %s', exc)

def identify_user(user_id: int, properties: dict = None):
    client = _get_posthog_client()
    if not client:
        return
    try:
        client.identify(
            distinct_id=str(user_id),
            properties=properties or {}
        )
    except Exception as exc:
        logger.warning('PostHog identify failed: %s', exc)

def is_feature_enabled(feature_flag_key: str, distinct_id: str) -> bool:
    client = _get_posthog_client()
    if not client:
        return False
    try:
        return client.feature_enabled(feature_flag_key, distinct_id)
    except Exception as exc:
        logger.warning('PostHog feature flag failed: %s', exc)
        return False
