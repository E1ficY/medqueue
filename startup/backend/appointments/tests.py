from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from django.test.utils import override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from datetime import timedelta

from .models import (
	Appointment,
	CardVerificationCode,
	Doctor,
	DoctorInviteCode,
	DoctorReview,
	Hospital,
	PasswordResetCode,
	PaymentCard,
	PaymentTransaction,
	UserProfile,
	VerificationCode,
)


class AIChatRecommendationTests(APITestCase):
	def test_ai_chat_uses_database_for_recommendation(self):
		hospital = Hospital.objects.create(
			name='Городская поликлиника N1',
			type='Поликлиника',
			address='г. Алматы, ул. Абая 10',
			phone='+7 777 000 00 01',
			waiting_time=8,
			is_active=True,
		)
		doctor = Doctor.objects.create(
			hospital=hospital,
			full_name='Иванов Иван Иванович',
			specialty='Терапевт',
			cabinet='101',
			is_active=True,
		)
		DoctorReview.objects.create(
			doctor=doctor,
			patient_name='Пациент А',
			rating=5,
			comment='Отличный прием',
		)

		with patch.dict('os.environ', {'HF_TOKEN': '', 'GEMINI_API_KEY': ''}, clear=False):
			response = self.client.post(
				'/api/ai/chat/',
				data={'message': 'У меня кашель и температура, порекомендуй врача'},
				format='json',
			)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertIn('reply', response.data)
		self.assertEqual(response.data.get('model'), 'medqueue-local')
		self.assertIn(doctor.full_name, response.data['reply'])
		self.assertIn(hospital.name, response.data['reply'])
		self.assertNotIn('Лучший вариант', response.data['reply'])
		self.assertNotIn('Еще варианты:', response.data['reply'])

	def test_ai_chat_requires_message(self):
		response = self.client.post('/api/ai/chat/', data={'message': ''}, format='json')
		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

	def test_ai_chat_fallbacks_to_all_doctors_if_specialty_not_found(self):
		hospital = Hospital.objects.create(
			name='Городская поликлиника N2',
			type='Поликлиника',
			address='г. Алматы, ул. Назарбаева 25',
			phone='+7 777 000 00 02',
			waiting_time=10,
			is_active=True,
		)
		doctor = Doctor.objects.create(
			hospital=hospital,
			full_name='Петров Петр Петрович',
			specialty='Уролог',
			is_active=True,
		)

		with patch.dict('os.environ', {'HF_TOKEN': '', 'GEMINI_API_KEY': ''}, clear=False):
			response = self.client.post(
				'/api/ai/chat/',
				data={'message': 'Посоветуй врача, не знаю к кому идти'},
				format='json',
			)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertIn(doctor.full_name, response.data['reply'])


class WaitingTimeLogicTests(TestCase):
	def setUp(self):
		self.hospital = Hospital.objects.create(
			name='Поликлиника Queue Test',
			type='Поликлиника',
			address='г. Алматы, ул. Сейфуллина 22',
			phone='+7 777 111 22 33',
			waiting_time=8,
			is_active=True,
		)

	def test_hospital_waiting_time_is_zero_when_queue_empty(self):
		self.assertEqual(self.hospital.current_queue, 0)
		self.assertEqual(self.hospital.estimated_waiting_time, 0)

	def test_hospital_waiting_time_depends_on_queue_count(self):
		base_dt = timezone.now() + timedelta(hours=2)
		Appointment.objects.create(
			patient_name='Пациент 1',
			hospital=self.hospital,
			specialty='Терапевт',
			datetime=base_dt,
			status='confirmed',
		)
		Appointment.objects.create(
			patient_name='Пациент 2',
			hospital=self.hospital,
			specialty='Терапевт',
			datetime=base_dt + timedelta(minutes=30),
			status='confirmed',
		)

		self.hospital.refresh_from_db()
		self.assertEqual(self.hospital.current_queue, 2)
		self.assertEqual(self.hospital.estimated_waiting_time, 30)
		self.assertIn('2 чел. x 15 мин = 30 мин', self.hospital.waiting_time_reason)

	def test_appointment_wait_time_is_zero_for_first_and_scaled_for_next(self):
		base_dt = timezone.now() + timedelta(hours=3)
		first = Appointment.objects.create(
			patient_name='Первый',
			hospital=self.hospital,
			specialty='Терапевт',
			datetime=base_dt,
			status='confirmed',
		)
		second = Appointment.objects.create(
			patient_name='Второй',
			hospital=self.hospital,
			specialty='Терапевт',
			datetime=base_dt + timedelta(minutes=20),
			status='confirmed',
		)

		self.assertEqual(first.estimated_wait_time, 0)
		self.assertIn('0 минут', first.estimated_wait_reason)
		self.assertEqual(second.queue_position, 2)
		self.assertEqual(second.estimated_wait_time, 15)
		self.assertIn('Перед вами 1 чел.', second.estimated_wait_reason)


class DoctorRatingTests(TestCase):
	def test_doctor_avg_rating_and_reviews_count(self):
		hospital = Hospital.objects.create(
			name='Рейтинговая клиника',
			type='Поликлиника',
			address='г. Алматы, ул. Жарокова 9',
			waiting_time=12,
			is_active=True,
		)
		doctor = Doctor.objects.create(
			hospital=hospital,
			full_name='Сагынбаев Даурен',
			specialty='Кардиолог',
			is_active=True,
		)

		DoctorReview.objects.create(doctor=doctor, patient_name='Пациент 1', rating=5, comment='Супер')
		DoctorReview.objects.create(doctor=doctor, patient_name='Пациент 2', rating=4, comment='Хорошо')

		self.assertEqual(doctor.reviews_count, 2)
		self.assertEqual(doctor.avg_rating, 4.5)
		self.assertEqual(hospital.avg_rating, 4.5)
		self.assertEqual(hospital.reviews_count, 2)


class DoctorPortalMedicalNotesTests(APITestCase):
	def test_doctor_can_save_exam_summary_and_medications(self):
		user = User.objects.create_user(
			username='doctor_case_1',
			email='doctor_case_1@example.com',
			password='StrongPass123!'
		)
		hospital = Hospital.objects.create(
			name='Тестовая больница врача',
			type='Больница',
			address='г. Алматы, ул. Тест 1',
			is_active=True,
		)
		doctor = Doctor.objects.create(
			hospital=hospital,
			user=user,
			full_name='Доктор Тест',
			specialty='Терапевт',
			is_active=True,
		)
		DoctorInviteCode.objects.create(
			code='MEDQ-TST111',
			hospital=hospital,
			specialty='Терапевт',
			is_used=True,
			used_by=user,
		)
		appointment = Appointment.objects.create(
			patient_name='Пациент Тест',
			hospital=hospital,
			doctor=doctor,
			specialty='Терапевт',
			datetime=timezone.now() + timedelta(days=1),
			status='confirmed',
		)

		self.client.force_authenticate(user=user)
		response = self.client.patch(
			f'/api/doctor/appointments/{appointment.id}/recommendation/',
			data={
				'doctor_recommendation': 'Отдых и питьевой режим',
				'exam_summary': 'ОРВИ без осложнений',
				'prescribed_medications': 'Парацетамол 500 мг 2 раза в день',
			},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		appointment.refresh_from_db()
		self.assertEqual(appointment.exam_summary, 'ОРВИ без осложнений')
		self.assertEqual(appointment.doctor_recommendation, 'Отдых и питьевой режим')


class DoctorReviewEndpointTests(APITestCase):
	def test_patient_can_create_doctor_review(self):
		patient = User.objects.create_user(
			username='patient_case_1',
			email='patient_case_1@example.com',
			password='StrongPass123!'
		)
		UserProfile.objects.create(user=patient, role='patient')

		hospital = Hospital.objects.create(
			name='Больница отзывов',
			type='Больница',
			address='г. Алматы, ул. Отзывная 7',
			is_active=True,
		)
		doctor = Doctor.objects.create(
			hospital=hospital,
			full_name='Отзывов Арман',
			specialty='Терапевт',
			is_active=True,
		)
		Appointment.objects.create(
			patient_name='Пациент Отзыв',
			hospital=hospital,
			doctor=doctor,
			specialty='Терапевт',
			datetime=timezone.now() - timedelta(days=1),
			status='completed',
			user=patient,
		)

		self.client.force_authenticate(user=patient)
		response = self.client.post(
			f'/api/reviews/doctors/{doctor.id}/',
			data={'rating': 5, 'comment': 'Очень хороший прием'},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		self.assertTrue(response.data.get('ok'))
		self.assertEqual(response.data['doctor']['avg_rating'], 5.0)
		self.assertEqual(response.data['doctor']['reviews_count'], 1)
		self.assertEqual(response.data['hospital']['avg_rating'], 5.0)
		self.assertEqual(response.data['hospital']['reviews_count'], 1)

	def test_patient_cannot_review_doctor_without_completed_appointment(self):
		patient = User.objects.create_user(
			username='patient_case_2',
			email='patient_case_2@example.com',
			password='StrongPass123!'
		)
		UserProfile.objects.create(user=patient, role='patient')

		hospital = Hospital.objects.create(
			name='Больница без завершения',
			type='Больница',
			address='г. Алматы, ул. БезОтзыва 8',
			is_active=True,
		)
		doctor = Doctor.objects.create(
			hospital=hospital,
			full_name='Нет Завершения',
			specialty='Терапевт',
			is_active=True,
		)

		self.client.force_authenticate(user=patient)
		response = self.client.post(
			f'/api/reviews/doctors/{doctor.id}/',
			data={'rating': 5, 'comment': 'Попытка без завершения'},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertIn('завершенного приема', response.data.get('error', '').lower())


class DoctorsCatalogApiTests(APITestCase):
	def test_public_doctors_catalog_returns_rating_and_hospital(self):
		hospital = Hospital.objects.create(
			name='Каталог больница',
			type='Больница',
			address='г. Алматы, ул. Каталог 1',
			is_active=True,
		)
		doctor = Doctor.objects.create(
			hospital=hospital,
			full_name='Каталог Айжан',
			specialty='Терапевт',
			is_active=True,
		)
		DoctorReview.objects.create(doctor=doctor, patient_name='Пациент 1', rating=5, comment='Отлично')

		response = self.client.get('/api/doctors/')
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertGreaterEqual(len(response.data), 1)
		item = next((x for x in response.data if x['id'] == doctor.id), None)
		self.assertIsNotNone(item)
		self.assertEqual(item['hospital_name'], hospital.name)
		self.assertEqual(item['avg_rating'], 5.0)

	def test_doctors_catalog_can_filter_by_specialty(self):
		hospital = Hospital.objects.create(
			name='Фильтр больница',
			type='Поликлиника',
			address='г. Алматы, ул. Фильтр 2',
			is_active=True,
		)
		Doctor.objects.create(hospital=hospital, full_name='Врач Терапевт', specialty='Терапевт', is_active=True)
		Doctor.objects.create(hospital=hospital, full_name='Врач Кардио', specialty='Кардиолог', is_active=True)

		response = self.client.get('/api/doctors/?specialty=Кардиолог')
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(response.data), 1)
		self.assertEqual(response.data[0]['specialty'], 'Кардиолог')


class AINameLookupTests(APITestCase):
	def test_ai_chat_finds_doctor_by_name_lookup(self):
		hospital = Hospital.objects.create(
			name='Поисковая клиника',
			type='Больница',
			address='г. Алматы, ул. Поиск 12',
			phone='+7 727 111 22 33',
			is_active=True,
		)
		doctor = Doctor.objects.create(
			hospital=hospital,
			full_name='Мерлан Захарович Тлеубеков',
			specialty='Терапевт',
			is_active=True,
		)

		response = self.client.post(
			'/api/ai/chat/',
			data={'message': 'Есть ли у вас врач Мерлан Захарович?'},
			format='json',
		)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data.get('model'), 'medqueue-db-name')
		self.assertIn(doctor.full_name, response.data.get('reply', ''))

	def test_generic_medical_question_does_not_force_name_lookup(self):
		hospital = Hospital.objects.create(
			name='Нейтральная клиника',
			type='Больница',
			address='г. Алматы, ул. Нейтральная 9',
			is_active=True,
		)
		Doctor.objects.create(
			hospital=hospital,
			full_name='Иванченко Виктор Олегович',
			specialty='Стоматолог',
			is_active=True,
		)

		response = self.client.post(
			'/api/ai/chat/',
			data={'message': 'У меня болит горло, к какому врачу обратиться?'},
			format='json',
		)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertNotEqual(response.data.get('model'), 'medqueue-db-name')

	def test_ai_chat_can_list_all_doctors(self):
		hospital = Hospital.objects.create(
			name='Сводная больница',
			type='Больница',
			address='г. Алматы, ул. Сводная 8',
			phone='+7 727 888 77 66',
			is_active=True,
		)
		d1 = Doctor.objects.create(hospital=hospital, full_name='Алиев Нурлан', specialty='Терапевт', is_active=True)
		d2 = Doctor.objects.create(hospital=hospital, full_name='Серикова Айгерим', specialty='Хирург', is_active=True)

		response = self.client.post(
			'/api/ai/chat/',
			data={'message': 'Покажи всех врачей из базы'},
			format='json',
		)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data.get('model'), 'medqueue-db-all')
		reply = response.data.get('reply', '')
		self.assertIn(d1.full_name, reply)
		self.assertIn(d2.full_name, reply)

	def test_ai_chat_can_list_doctors_by_specialty(self):
		hospital = Hospital.objects.create(
			name='Спец клиника',
			type='Больница',
			address='г. Алматы, ул. Спец 15',
			is_active=True,
		)
		surgeon = Doctor.objects.create(hospital=hospital, full_name='Хирург Тестовый', specialty='Хирург', is_active=True)
		therapist = Doctor.objects.create(hospital=hospital, full_name='Терапевт Тестовый', specialty='Терапевт', is_active=True)

		response = self.client.post(
			'/api/ai/chat/',
			data={'message': 'Покажи все хирурги'},
			format='json',
		)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data.get('model'), 'medqueue-db-all')
		reply = response.data.get('reply', '')
		self.assertIn(surgeon.full_name, reply)
		self.assertNotIn(therapist.full_name, reply)


@override_settings(EMAIL_HOST_USER='noreply@medqueue.test')
class AuthFlowTests(APITestCase):
	def test_register_verify_and_login_patient_flow(self):
		with patch('appointments.auth_views.verify_recaptcha_token', return_value=True), patch('appointments.auth_views.send_mail'):
			register_payload = {
				'name': 'Test Patient',
				'email': 'patient_auth_flow@example.com',
				'username': 'patient_auth_flow',
				'password': 'StrongPass123!@#',
				'role': 'patient',
				'captcha_token': 'ok-token',
			}
			register_response = self.client.post('/api/auth/register/', data=register_payload, format='json')

		self.assertEqual(register_response.status_code, status.HTTP_200_OK)
		user = User.objects.get(email='patient_auth_flow@example.com')
		self.assertFalse(user.is_active)

		verification = user and user.email
		self.assertTrue(verification)
		verification_code = VerificationCode.objects.filter(email=user.email).order_by('-created_at').first()
		self.assertIsNotNone(verification_code)

		verify_response = self.client.post(
			'/api/auth/verify/',
			data={'email': user.email, 'code': verification_code.code},
			format='json',
		)
		self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
		user.refresh_from_db()
		self.assertTrue(user.is_active)
		self.assertEqual(user.profile.role, 'patient')

		with patch('appointments.auth_views.verify_recaptcha_token', return_value=True):
			login_response = self.client.post(
				'/api/auth/login/',
				data={'login': 'patient_auth_flow', 'password': 'StrongPass123!@#', 'captcha_token': 'ok-token'},
				format='json',
			)
		self.assertEqual(login_response.status_code, status.HTTP_200_OK)
		self.assertIn('access', login_response.data)

	def test_register_doctor_requires_valid_invite_code(self):
		with patch('appointments.auth_views.verify_recaptcha_token', return_value=True):
			response = self.client.post(
				'/api/auth/register/',
				data={
					'name': 'Doctor Candidate',
					'email': 'doctor_candidate@example.com',
					'username': 'doctor_candidate',
					'password': 'StrongPass123!@#',
					'role': 'doctor',
					'captcha_token': 'ok-token',
				},
				format='json',
			)

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertIn('код приглашения', response.data.get('error', '').lower())


@override_settings(EMAIL_HOST_USER='noreply@medqueue.test')
class PasswordResetFlowTests(APITestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username='reset_flow_user',
			email='reset_flow_user@example.com',
			password='OldPass123!@#',
			first_name='Reset User',
			is_active=True,
		)

	def test_password_reset_request_and_confirm(self):
		with patch('appointments.auth_views.send_mail'):
			request_resp = self.client.post(
				'/api/auth/password-reset/',
				data={'email': self.user.email},
				format='json',
			)

		self.assertEqual(request_resp.status_code, status.HTTP_200_OK)

		reset_code = PasswordResetCode.objects.filter(email=self.user.email).order_by('-created_at').first()
		self.assertIsNotNone(reset_code)

		confirm_resp = self.client.post(
			'/api/auth/password-reset/confirm/',
			data={
				'email': self.user.email,
				'code': reset_code.code,
				'new_password': 'NewPass123!@#',
			},
			format='json',
		)
		self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK)
		self.assertIn('access', confirm_resp.data)

		self.user.refresh_from_db()
		self.assertTrue(self.user.check_password('NewPass123!@#'))


class DoctorCodeValidationTests(APITestCase):
	def test_validate_doctor_code_success(self):
		hospital = Hospital.objects.create(
			name='Invite Hospital',
			type='Больница',
			address='г. Алматы, ул. Инвайт 1',
			is_active=True,
		)
		DoctorInviteCode.objects.create(
			code='MEDQ-ABC123',
			hospital=hospital,
			specialty='Терапевт',
			is_used=False,
		)

		response = self.client.post('/api/auth/validate-doctor-code/', data={'code': 'MEDQ-ABC123'}, format='json')
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertTrue(response.data.get('valid'))
		self.assertEqual(response.data.get('hospital'), hospital.name)


class SubscriptionFlowTests(APITestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username='sub_patient',
			email='sub_patient@example.com',
			password='SubPass123!@#',
			first_name='Sub Patient',
			is_active=True,
		)
		UserProfile.objects.create(user=self.user, role='patient')
		self.client.force_authenticate(user=self.user)

	def test_subscription_me_returns_default_plan(self):
		response = self.client.get('/api/subscription/me/')
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['subscription']['plan_id'], 'free')
		self.assertIsNone(response.data['card'])

	def test_plus_activation_requires_card(self):
		response = self.client.post('/api/subscription/activate/', data={'plan_id': 'plus'}, format='json')
		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertIn('сначала добавьте платежную карту', response.data.get('error', '').lower())

	def test_card_save_verify_and_plus_activation_success(self):
		save_resp = self.client.post(
			'/api/subscription/card/',
			data={
				'card_number': '4242424242424242',
				'card_holder': 'SUB PATIENT',
				'exp_month': 12,
				'exp_year': timezone.localtime().year + 2,
				'cvc': '123',
			},
			format='json',
		)
		self.assertEqual(save_resp.status_code, status.HTTP_200_OK)
		self.assertTrue(save_resp.data.get('requires_verification'))

		verify = CardVerificationCode.objects.filter(user=self.user, is_used=False).order_by('-created_at').first()
		self.assertIsNotNone(verify)

		verify_resp = self.client.post('/api/subscription/card/verify/', data={'code': verify.code}, format='json')
		self.assertEqual(verify_resp.status_code, status.HTTP_200_OK)
		self.assertTrue(verify_resp.data['card']['is_verified'])

		activate_resp = self.client.post('/api/subscription/activate/', data={'plan_id': 'plus'}, format='json')
		self.assertEqual(activate_resp.status_code, status.HTTP_200_OK)
		self.assertEqual(activate_resp.data['subscription']['plan_id'], 'plus')
		self.assertIn('payment_receipt', activate_resp.data)

	def test_subscription_reset_demo_clears_payment_data(self):
		PaymentCard.objects.create(
			user=self.user,
			card_holder='SUB PATIENT',
			brand='VISA',
			last4='4242',
			exp_month=12,
			exp_year=timezone.localtime().year + 2,
			token='TOK123',
			is_verified=True,
		)
		PaymentTransaction.objects.create(
			user=self.user,
			amount=2990,
			currency='KZT',
			status='paid',
			transaction_ref='MQPTEST0001',
			card_last4='4242',
			card_brand='VISA',
		)

		response = self.client.post('/api/subscription/reset-demo/', data={}, format='json')
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertTrue(response.data.get('ok'))
		self.assertEqual(response.data['subscription']['plan_id'], 'free')
		self.assertEqual(PaymentCard.objects.filter(user=self.user).count(), 0)
		self.assertEqual(PaymentTransaction.objects.filter(user=self.user).count(), 0)
		self.assertEqual(CardVerificationCode.objects.filter(user=self.user).count(), 0)
