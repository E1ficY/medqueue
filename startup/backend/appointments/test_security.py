import os
import json
from unittest.mock import patch
from django.contrib.auth.models import User
from django.utils import timezone
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import UserProfile, Appointment, Hospital

class SecurityEnhancementsTests(APITestCase):

    def setUp(self):
        # Create standard test users
        self.patient_user = User.objects.create_user(
            username='patient_user',
            email='patient@medqueue.kz',
            password='StrongPassword123!'
        )
        self.patient_profile = UserProfile.objects.create(
            user=self.patient_user,
            role='patient'
        )

        self.admin_user = User.objects.create_user(
            username='admin_user',
            email='admin@medqueue.kz',
            password='StrongPassword123!'
        )
        self.admin_profile = UserProfile.objects.create(
            user=self.admin_user,
            role='admin'
        )

        self.other_patient = User.objects.create_user(
            username='other_patient',
            email='other@medqueue.kz',
            password='StrongPassword123!'
        )
        self.other_profile = UserProfile.objects.create(
            user=self.other_patient,
            role='patient'
        )

        self.hospital = Hospital.objects.create(
            name='Test Hospital',
            type='Поликлиника',
            address='г. Алматы'
        )

    # 1. Test Password Strength Validation (HTTP 422)
    def test_register_password_strength_validation_fails(self):
        # Attempt register with a weak password (no digit, less than 8 chars)
        register_payload = {
            'name': 'Weak Password User',
            'email': 'weakpass@example.com',
            'username': 'weakpassuser',
            'password': 'short',
            'role': 'patient',
            'captcha_token': 'ok-token'
        }
        with patch('appointments.auth_views.verify_recaptcha_token', return_value=True):
            response = self.client.post(
                '/api/auth/register/',
                data=register_payload,
                format='json'
            )
        self.assertEqual(response.status_code, 422)
        self.assertIn("Пароль должен содержать не менее 8 символов.", response.json()['error'])
        self.assertIn("Пароль должен содержать как минимум одну цифру.", response.json()['error'])

    # 2. Test SimpleJWT Custom Claims (id & role)
    def test_jwt_tokens_contain_custom_claims(self):
        from .auth_views import get_tokens_for_user
        tokens = get_tokens_for_user(self.patient_user)
        access_token = tokens['access']
        
        # Decode token to verify claims
        from rest_framework_simplejwt.tokens import AccessToken
        decoded = AccessToken(access_token)
        self.assertEqual(decoded['role'], 'patient')
        self.assertEqual(decoded['id'], self.patient_user.id)

    # 3. Test OAuth2 Authentication Endpoints (Google & Facebook)
    @patch('urllib.request.urlopen')
    def test_google_oauth2_success(self, mock_urlopen):
        # Mock Google UserInfo API response
        mock_response = mock_urlopen.return_value.__enter__.return_value
        mock_response.read.return_value = json.dumps({
            'email': 'google_oauth_user@example.com',
            'name': 'Google OAuth User',
            'given_name': 'Google'
        }).encode('utf-8')

        response = self.client.post(
            '/api/auth/google/',
            data={'access_token': 'valid-google-token'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['user']['email'], 'google_oauth_user@example.com')
        self.assertEqual(response.data['user']['role'], 'patient')

    @patch('urllib.request.urlopen')
    def test_facebook_oauth2_success(self, mock_urlopen):
        # Mock Facebook Graph API response
        mock_response = mock_urlopen.return_value.__enter__.return_value
        mock_response.read.return_value = json.dumps({
            'id': '1234567890',
            'name': 'Facebook OAuth User',
            'email': 'fb_oauth_user@example.com'
        }).encode('utf-8')

        response = self.client.post(
            '/api/auth/facebook/',
            data={'access_token': 'valid-fb-token'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['user']['email'], 'fb_oauth_user@example.com')
        self.assertEqual(response.data['user']['role'], 'patient')

    # 4. Test Custom DRF Permissions (RBAC & BOLA / OWASP A01)
    def test_update_comment_bola_protection(self):
        # Create an appointment owned by patient_user
        appointment = Appointment.objects.create(
            patient_name='Patient Appointment',
            hospital=self.hospital,
            specialty='Терапевт',
            datetime=timezone.now(),
            user=self.patient_user
        )

        # 1. Other user attempts to update comment (Should fail - 403 Forbidden)
        self.client.force_authenticate(user=self.other_patient)
        response = self.client.patch(
            '/api/appointments/update_comment/',
            data={'code': appointment.code, 'comment': 'unauthorized change'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Creator user updates comment (Should succeed - 200 OK)
        self.client.force_authenticate(user=self.patient_user)
        response = self.client.post(  # Note: view uses PATCH in route but mapped inside action
            '/api/appointments/update_comment/',
            data={'code': appointment.code, 'comment': 'authorized change'},
            format='json'
        )
        # Note: the update_comment action is defined with methods=['patch'] in the viewset, 
        # so let's call patch
        response = self.client.patch(
            '/api/appointments/update_comment/',
            data={'code': appointment.code, 'comment': 'authorized change'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        appointment.refresh_from_db()
        self.assertEqual(appointment.comment, 'authorized change')

        # 3. Admin user updates comment (Should succeed - 200 OK)
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.patch(
            '/api/appointments/update_comment/',
            data={'code': appointment.code, 'comment': 'admin change'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        appointment.refresh_from_db()
        self.assertEqual(appointment.comment, 'admin change')

    # 5. Test Middlewares (Security Headers & Admin RBAC)
    def test_security_headers_middleware_injected(self):
        response = self.client.get('/api/hospitals/')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response['X-Frame-Options'], 'DENY')
        self.assertEqual(response['Referrer-Policy'], 'strict-origin-when-cross-origin')
        self.assertIn('Strict-Transport-Security', response)
        self.assertIn('Content-Security-Policy', response)
        self.assertIn('Permissions-Policy', response)

    def test_admin_rbac_middleware_restrictions(self):
        # Patient user tries to access /api/admin/stats/ (Should fail - 403 Forbidden)
        refresh = RefreshToken.for_user(self.patient_user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        response = self.client.get('/api/admin/stats/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Admin user tries to access /api/admin/stats/ (Should succeed - 200 OK)
        refresh_admin = RefreshToken.for_user(self.admin_user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh_admin.access_token}')
        response = self.client.get('/api/admin/stats/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


    # 6. Test JSON Security Logging for Failed Logins
    def test_failed_login_logs_security_event_as_json(self):
        with patch('appointments.auth_views.verify_recaptcha_token', return_value=True):
            response = self.client.post(
                '/api/auth/login/',
                data={'login': 'non_existent_user', 'password': 'wrong_password', 'captcha_token': 'ok-token'},
                format='json'
            )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        
        # Verify JSON log file exists and contains FAILED_LOGIN event
        from django.conf import settings
        log_file = os.path.join(settings.BASE_DIR, 'logs', 'security.log')
        self.assertTrue(os.path.exists(log_file))
        
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        last_line = json.loads(lines[-1].strip())
        self.assertEqual(last_line['event'], 'FAILED_LOGIN')
        self.assertEqual(last_line['email'], 'non_existent_user')
        self.assertIn('ip', last_line)
        self.assertIn('user_agent', last_line)
