from collections import defaultdict
from datetime import timedelta
import random
import string
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.contrib.auth.models import User
from .models import (
    Hospital, Appointment, Doctor, DoctorInviteCode, UserProfile,
    UserSubscription, PaymentCard, PaymentTransaction, CardVerificationCode,
    SPECIALTIES_CHOICES,
)
from .serializers import (
    HospitalSerializer,
    HospitalDetailSerializer,
    AppointmentCreateSerializer,
    AppointmentStatusSerializer,
    DoctorSerializer,
)


class HospitalViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API для больниц — только чтение, доступно всем.

    GET /api/hospitals/        — список всех активных больниц (без пагинации)
    GET /api/hospitals/{id}/   — детальная карточка больницы
    GET /api/hospitals/{id}/doctors/ — врачи больницы, сгруппированные по специальностям
    """
    permission_classes = [AllowAny]
    pagination_class = None  # возвращаем полный список без пагинации

    def get_queryset(self):
        """Возвращаем только активные больницы"""
        return Hospital.objects.filter(is_active=True)

    def get_serializer_class(self):
        """Для детального запроса используем расширенный сериализатор"""
        if self.action == 'retrieve':
            return HospitalDetailSerializer
        return HospitalSerializer

    @action(detail=True, methods=['get'], url_path='doctors')
    def doctors(self, request, pk=None):
        """
        Врачи больницы, сгруппированные по специальностям.

        GET /api/hospitals/{id}/doctors/
        Ответ: [{specialty: "Терапевт", doctors: [{id, full_name, cabinet, ...}]}]
        """
        hospital = get_object_or_404(Hospital, pk=pk, is_active=True)
        # Выбираем только активных врачей данной больницы
        doctors_qs = Doctor.objects.filter(
            hospital=hospital, is_active=True
        ).order_by('specialty', 'full_name')

        # Группируем по специальности
        grouped = defaultdict(list)
        for doc in doctors_qs:
            grouped[doc.specialty].append(DoctorSerializer(doc).data)

        result = [
            {'specialty': spec, 'doctors': docs}
            for spec, docs in sorted(grouped.items())
        ]
        return Response(result)


class AppointmentViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    """
    API для записей на приём.

    POST /api/appointments/                    — создать запись (гость или авторизованный)
    GET  /api/appointments/check/{code}/       — проверить статус по коду (публичный)
    POST /api/appointments/cancel/             — отменить запись по коду (публичный)
    GET  /api/appointments/my_appointments/    — мои записи (требует авторизации)
    """
    queryset = Appointment.objects.all()
    serializer_class = AppointmentStatusSerializer
    # Создание, проверка и отмена — публичные; my_appointments переопределяет
    permission_classes = [AllowAny]

    def get_serializer_class(self):
        """Выбираем сериализатор в зависимости от действия"""
        if self.action == 'create':
            return AppointmentCreateSerializer
        return AppointmentStatusSerializer

    def create(self, request):
        """
        Создать новую запись (доступно гостям и авторизованным пользователям).

        POST /api/appointments/
        Body: {
            "patient_name": "Иван Иванов",
            "hospital": 1,
            "specialty": "Терапевт",
            "datetime": "2025-01-27T10:00:00",
            "doctor": 3  // необязательно
        }
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Привязываем к пользователю только если он авторизован
        user = request.user if request.user.is_authenticated else None
        appointment = serializer.save(user=user)

        # Возвращаем полную информацию о созданной записи
        response_serializer = AppointmentStatusSerializer(appointment)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], url_path='check/(?P<code>[A-Z0-9]{6})',
            permission_classes=[AllowAny])
    def check_status(self, request, code=None):
        """
        Проверить статус записи по коду.

        GET /api/appointments/check/{CODE}/
        """
        appointment = get_object_or_404(Appointment, code=code.upper())
        serializer = self.get_serializer(appointment)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='cancel',
            permission_classes=[AllowAny])
    def cancel_appointment(self, request):
        """
        Отменить запись по коду.

        POST /api/appointments/cancel/
        Body: {"code": "ABC123"}
        """
        code = request.data.get('code', '').upper()

        if not code:
            return Response(
                {'error': 'Код записи обязателен'},
                status=status.HTTP_400_BAD_REQUEST
            )

        appointment = get_object_or_404(Appointment, code=code)

        if appointment.status == 'cancelled':
            return Response(
                {'error': 'Запись уже отменена'},
                status=status.HTTP_400_BAD_REQUEST
            )

        appointment.status = 'cancelled'
        appointment.save()

        # Пересчитываем позиции оставшихся в очереди на тот же день
        same_day = Appointment.objects.filter(
            hospital=appointment.hospital,
            datetime__date=appointment.datetime.date(),
            status='confirmed'
        ).order_by('datetime')
        for i, appt in enumerate(same_day, start=1):
            if appt.queue_position != i:
                appt.queue_position = i
                appt.save(update_fields=['queue_position'])

        return Response({
            'message': 'Запись успешно отменена',
            'code': code
        })

    @action(detail=False, methods=['patch'], url_path='update_comment',
            permission_classes=[IsAuthenticated])
    def update_comment(self, request):
        """
        Обновить/добавить комментарий к записи по коду.

        PATCH /api/appointments/update_comment/
        Body: {"code": "ABC123", "comment": "текст комментария"}
        """
        code = request.data.get('code', '').upper()
        comment = request.data.get('comment', '')

        if not code:
            return Response(
                {'error': 'Код записи обязателен'},
                status=status.HTTP_400_BAD_REQUEST
            )

        appointment = get_object_or_404(Appointment, code=code)

        # Только владелец записи может менять комментарий.
        if appointment.user != request.user:
            return Response(
                {'error': 'Нет доступа'},
                status=status.HTTP_403_FORBIDDEN
            )

        appointment.comment = comment.strip()
        appointment.save(update_fields=['comment'])

        serializer = AppointmentStatusSerializer(appointment)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_appointments(self, request):
        """
        Записи текущего авторизованного пользователя.

        GET /api/appointments/my_appointments/
        Требует: Authorization: Bearer <access_token>
        """
        appointments = Appointment.objects.filter(
            user=request.user
        ).order_by('-created_at')
        serializer = AppointmentStatusSerializer(appointments, many=True)
        return Response(serializer.data)


# ─────────────────────────────────────────────
#  SUBSCRIPTIONS (ONLY PATIENTS)
# ─────────────────────────────────────────────

SUBSCRIPTION_PLANS = {
    'free': {
        'id': 'free',
        'title': 'Start',
        'price_kzt': 0,
        'period': 'month',
        'is_popular': False,
        'benefits': [
            'Онлайн-запись к врачу и статус очереди',
            'Личный кабинет и история приёмов',
            'Уведомления о времени приёма',
        ],
    },
    'plus': {
        'id': 'plus',
        'title': 'Care Plus',
        'price_kzt': 2990,
        'period': 'month',
        'is_popular': True,
        'benefits': [
            'Приоритетные временные слоты в популярных клиниках',
            'Расширенные напоминания и рекомендации после приёма',
            'Автоматический заказ такси после завершения приёма',
        ],
    },
}


def _get_user_role(user):
    profile = getattr(user, 'profile', None)
    return profile.role if profile else 'patient'


def _require_patient(request):
    if not request.user.is_authenticated:
        return None, Response({'error': 'Требуется авторизация'}, status=401)
    role = _get_user_role(request.user)
    if role != 'patient':
        return None, Response({'error': 'Подписка доступна только пользователям-пациентам'}, status=403)
    return request.user, None


def _detect_card_brand(card_number: str):
    if card_number.startswith('4'):
        return 'VISA'
    if card_number[:2] in {'51', '52', '53', '54', '55'} or card_number.startswith('2'):
        return 'MASTERCARD'
    if card_number.startswith('34') or card_number.startswith('37'):
        return 'AMEX'
    return 'CARD'


def _make_tx_ref():
    suffix = ''.join(random.choices(string.digits, k=8))
    return f"MQP{timezone.now().strftime('%y%m%d')}{suffix}"


def _issue_card_verification_code(user, card):
    CardVerificationCode.objects.filter(user=user, is_used=False).delete()
    code = ''.join(random.choices(string.digits, k=6))
    expires_at = timezone.now() + timedelta(minutes=10)
    return CardVerificationCode.objects.create(
        user=user,
        card=card,
        code=code,
        expires_at=expires_at,
    )


@api_view(['GET'])
@permission_classes([AllowAny])
def subscription_plans(request):
    """GET /api/subscription/plans/ — публичный список планов."""
    return Response({'plans': [SUBSCRIPTION_PLANS['free'], SUBSCRIPTION_PLANS['plus']]})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def subscription_me(request):
    """GET /api/subscription/me/ — текущая подписка пациента + карта + платежи."""
    user, err = _require_patient(request)
    if err:
        return err

    sub, _ = UserSubscription.objects.get_or_create(
        user=user,
        defaults={'plan': 'free', 'status': 'active', 'auto_taxi_enabled': False}
    )
    plan_data = SUBSCRIPTION_PLANS.get(sub.plan, SUBSCRIPTION_PLANS['free'])

    card = PaymentCard.objects.filter(user=user).first()
    txs = PaymentTransaction.objects.filter(user=user)[:5]
    pending_code = CardVerificationCode.objects.filter(user=user, is_used=False).order_by('-created_at').first()

    return Response({
        'subscription': {
            'plan_id': sub.plan,
            'plan_title': plan_data['title'],
            'status': sub.status,
            'price_kzt': plan_data['price_kzt'],
            'benefits': plan_data['benefits'],
            'auto_taxi_enabled': sub.auto_taxi_enabled,
            'started_at': sub.started_at.isoformat() if sub.started_at else None,
            'next_billing_date': sub.next_billing_date.isoformat() if sub.next_billing_date else None,
        },
        'card': {
            'card_holder': card.card_holder,
            'brand': card.brand,
            'last4': card.last4,
            'masked_pan': f"**** **** **** {card.last4}",
            'exp_month': card.exp_month,
            'exp_year': card.exp_year,
            'is_verified': card.is_verified,
        } if card else None,
        'card_verification_required': bool(card and not card.is_verified),
        'card_verification_expires_at': pending_code.expires_at.isoformat() if pending_code and not pending_code.is_expired() else None,
        'transactions': [
            {
                'transaction_ref': t.transaction_ref,
                'amount': float(t.amount),
                'currency': t.currency,
                'status': t.status,
                'merchant_name': t.merchant_name,
                'description': t.description,
                'authorization_code': t.authorization_code,
                'card_masked': (f"{t.card_brand} •••• {t.card_last4}" if t.card_last4 else '—'),
                'paid_at': t.paid_at.isoformat() if t.paid_at else None,
                'created_at': t.created_at.isoformat(),
            }
            for t in txs
        ]
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def subscription_save_card(request):
    """POST /api/subscription/card/ — сохранить карту пациента и запросить код подтверждения."""
    user, err = _require_patient(request)
    if err:
        return err

    card_number = ''.join(ch for ch in str(request.data.get('card_number', '')) if ch.isdigit())
    card_holder = (request.data.get('card_holder') or '').strip()
    exp_month = int(request.data.get('exp_month') or 0)
    exp_year = int(request.data.get('exp_year') or 0)
    cvc = ''.join(ch for ch in str(request.data.get('cvc', '')) if ch.isdigit())

    if len(card_number) < 12 or len(card_number) > 19:
        return Response({'error': 'Некорректный номер карты'}, status=400)
    if not card_holder or len(card_holder) < 3:
        return Response({'error': 'Укажите имя держателя карты'}, status=400)
    if exp_month < 1 or exp_month > 12:
        return Response({'error': 'Некорректный месяц действия карты'}, status=400)
    current_year = timezone.now().year
    if exp_year < current_year or exp_year > current_year + 15:
        return Response({'error': 'Некорректный год действия карты'}, status=400)
    if len(cvc) < 3 or len(cvc) > 4:
        return Response({'error': 'Некорректный CVC/CVV код'}, status=400)

    brand = _detect_card_brand(card_number)
    last4 = card_number[-4:]
    token = ''.join(random.choices(string.ascii_uppercase + string.digits, k=24))

    card, _ = PaymentCard.objects.update_or_create(
        user=user,
        defaults={
            'card_holder': card_holder,
            'brand': brand,
            'last4': last4,
            'exp_month': exp_month,
            'exp_year': exp_year,
            'token': token,
            'is_verified': False,
        }
    )

    verify_obj = _issue_card_verification_code(user, card)

    return Response({
        'ok': True,
        'message': 'Карта сохранена. Введите код подтверждения от банка',
        'bank_message': f"Банк отправил SMS-код подтверждения на карту •••• {card.last4}",
        'requires_verification': True,
        'verification_expires_at': verify_obj.expires_at.isoformat(),
        'card': {
            'card_holder': card.card_holder,
            'brand': card.brand,
            'last4': card.last4,
            'masked_pan': f"**** **** **** {card.last4}",
            'exp_month': card.exp_month,
            'exp_year': card.exp_year,
            'is_verified': card.is_verified,
        }
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def subscription_verify_card(request):
    """POST /api/subscription/card/verify/ — подтверждение карты кодом из банка."""
    user, err = _require_patient(request)
    if err:
        return err

    code = ''.join(ch for ch in str(request.data.get('code', '')) if ch.isdigit())
    if len(code) != 6:
        return Response({'error': 'Введите 6-значный код подтверждения'}, status=400)

    card = PaymentCard.objects.filter(user=user).first()
    if not card:
        return Response({'error': 'Сначала добавьте карту'}, status=400)

    verify_obj = CardVerificationCode.objects.filter(user=user, is_used=False).order_by('-created_at').first()
    if not verify_obj:
        return Response({'error': 'Код подтверждения не найден. Добавьте карту снова'}, status=400)
    if verify_obj.is_expired():
        return Response({'error': 'Код подтверждения истёк. Запросите новый'}, status=400)
    if verify_obj.code != code:
        return Response({'error': 'Неверный код подтверждения'}, status=400)

    verify_obj.is_used = True
    verify_obj.save(update_fields=['is_used'])
    card.is_verified = True
    card.save(update_fields=['is_verified', 'updated_at'])

    return Response({
        'ok': True,
        'message': 'Карта успешно подтверждена',
        'card': {
            'card_holder': card.card_holder,
            'brand': card.brand,
            'last4': card.last4,
            'masked_pan': f"**** **** **** {card.last4}",
            'exp_month': card.exp_month,
            'exp_year': card.exp_year,
            'is_verified': card.is_verified,
        }
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def subscription_activate(request):
    """POST /api/subscription/activate/ — активировать выбранный тариф."""
    user, err = _require_patient(request)
    if err:
        return err

    plan_id = (request.data.get('plan_id') or 'free').strip().lower()
    if plan_id not in SUBSCRIPTION_PLANS:
        return Response({'error': 'Выбранный тариф не существует'}, status=400)

    sub, _ = UserSubscription.objects.get_or_create(
        user=user,
        defaults={'plan': 'free', 'status': 'active', 'auto_taxi_enabled': False}
    )
    selected = SUBSCRIPTION_PLANS[plan_id]
    card = PaymentCard.objects.filter(user=user).first()

    if plan_id == 'plus' and not card:
        return Response({'error': 'Для тарифа Care Plus сначала добавьте платежную карту'}, status=400)
    if plan_id == 'plus' and card and not card.is_verified:
        return Response({'error': 'Сначала подтвердите карту кодом из банка'}, status=400)

    amount = selected['price_kzt']
    transaction = PaymentTransaction.objects.create(
        user=user,
        subscription=sub,
        amount=amount,
        currency='KZT',
        status='processing',
        transaction_ref=_make_tx_ref(),
        merchant_name='MedQueue Health Services',
        card_last4=card.last4 if card else '',
        card_brand=card.brand if card else '',
        description=f"Оплата тарифа {selected['title']}",
    )

    # Симулируем реалистичный жизненный цикл платежа.
    transaction.status = 'paid'
    transaction.authorization_code = ''.join(random.choices(string.digits, k=6))
    transaction.paid_at = timezone.now()
    transaction.save(update_fields=['status', 'authorization_code', 'paid_at'])

    sub.plan = plan_id
    sub.status = 'active'
    sub.auto_taxi_enabled = (plan_id == 'plus')
    sub.next_billing_date = timezone.now().date() + timedelta(days=30) if plan_id == 'plus' else None
    sub.save(update_fields=['plan', 'status', 'auto_taxi_enabled', 'next_billing_date', 'updated_at'])

    return Response({
        'ok': True,
        'message': f"Тариф {selected['title']} успешно активирован",
        'subscription': {
            'plan_id': sub.plan,
            'plan_title': selected['title'],
            'price_kzt': selected['price_kzt'],
            'auto_taxi_enabled': sub.auto_taxi_enabled,
            'next_billing_date': sub.next_billing_date.isoformat() if sub.next_billing_date else None,
            'benefits': selected['benefits'],
        },
        'payment_receipt': {
            'status': transaction.status,
            'status_timeline': ['PROCESSING', 'AUTHORIZED', 'CAPTURED'],
            'transaction_ref': transaction.transaction_ref,
            'authorization_code': transaction.authorization_code,
            'amount': float(transaction.amount),
            'currency': transaction.currency,
            'merchant_name': transaction.merchant_name,
            'paid_at': transaction.paid_at.isoformat() if transaction.paid_at else None,
            'card_masked': f"{transaction.card_brand} •••• {transaction.card_last4}" if transaction.card_last4 else 'NO-CARD',
            'description': transaction.description,
        }
    })


# ─────────────────────────────────────────────
#  DOCTOR PORTAL  —  /api/doctor/...
# ─────────────────────────────────────────────

def _require_doctor(request):
    """
    Returns (hospital, doctor_entry, error_response).
    doctor_entry — запись Doctor, привязанная к аккаунту (может быть None для старых инвайт-кодов).
    """
    if not request.user.is_authenticated:
        return None, None, Response({'error': 'Требуется авторизация'}, status=401)
    try:
        invite = request.user.doctor_invite  # OneToOne from DoctorInviteCode
    except Exception:
        return None, None, Response({'error': 'Аккаунт врача не найден'}, status=403)
    if not invite.hospital:
        return None, None, Response({'error': 'Больница не привязана к вашему аккаунту'}, status=403)
    # Ищем конкретную запись Doctor, привязанную к этому пользователю
    doctor_entry = Doctor.objects.filter(user=request.user).first()
    return invite.hospital, doctor_entry, None


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def doctor_me(request):
    """
    GET /api/doctor/me/
    Возвращает профиль врача: имя, email, больница, специальность.
    """
    hospital, doctor_entry, err = _require_doctor(request)
    if err:
        return err

    invite = request.user.doctor_invite
    today = timezone.now().date()

    # Если врач привязан к конкретной записи Doctor — считаем только его записи
    if doctor_entry:
        today_count = Appointment.objects.filter(
            doctor=doctor_entry, datetime__date=today, status='confirmed'
        ).count()
        total_count = Appointment.objects.filter(doctor=doctor_entry).count()
    else:
        today_count = Appointment.objects.filter(
            hospital=hospital, datetime__date=today, status='confirmed'
        ).count()
        total_count = Appointment.objects.filter(hospital=hospital).count()

    return Response({
        'name': request.user.get_full_name() or request.user.first_name or request.user.username,
        'email': request.user.email,
        'specialty': (doctor_entry.specialty if doctor_entry else invite.specialty) or 'Не указана',
        'cabinet': doctor_entry.cabinet if doctor_entry else '',
        'work_days': doctor_entry.work_days if doctor_entry else 'Пн-Пт',
        'work_hours': doctor_entry.work_hours if doctor_entry else '08:00-18:00',
        'doctor_id': doctor_entry.id if doctor_entry else None,
        'hospital': {
            'id': hospital.id,
            'name': hospital.name,
            'address': hospital.address,
            'type': hospital.type,
        },
        'stats': {
            'today': today_count,
            'total': total_count,
        }
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def doctor_appointments(request):
    """
    GET /api/doctor/appointments/?filter=today|all&status=confirmed|cancelled|completed
    Записи пациентов к данному врачу.
    """
    hospital, doctor_entry, err = _require_doctor(request)
    if err:
        return err

    invite = request.user.doctor_invite

    # Если есть конкретная Doctor-запись — фильтруем строго по ней
    if doctor_entry:
        qs = Appointment.objects.filter(doctor=doctor_entry).order_by('datetime')
    else:
        # Fallback: фильтр по больнице + специальности (старые аккаунты без Doctor-записи)
        qs = Appointment.objects.filter(hospital=hospital).order_by('datetime')
        if invite.specialty:
            qs = qs.filter(specialty=invite.specialty)

    # Фильтр период
    period = request.GET.get('filter', 'today')
    if period == 'today':
        qs = qs.filter(datetime__date=timezone.now().date())
    elif period == 'week':
        from datetime import timedelta
        qs = qs.filter(datetime__date__gte=timezone.now().date(),
                       datetime__date__lte=timezone.now().date() + timedelta(days=7))

    # Фильтр статус
    status_filter = request.GET.get('status', '')
    if status_filter in ('confirmed', 'cancelled', 'completed'):
        qs = qs.filter(status=status_filter)

    data = []
    for appt in qs:
        data.append({
            'id': appt.id,
            'code': appt.code,
            'patient_name': appt.patient_name,
            'specialty': appt.specialty,
            'datetime': appt.datetime.isoformat(),
            'queue_position': appt.queue_position,
            'status': appt.status,
            'user_email': appt.user.email if appt.user else None,
            'comment': appt.comment or '',
            'doctor_recommendation': appt.doctor_recommendation or '',
        })

    return Response(data)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def doctor_update_appointment(request, appointment_id):
    """
    PATCH /api/doctor/appointments/<id>/
    Body: {"status": "completed" | "cancelled" | "confirmed"}
    Врач может менять статус только своих записей.
    """
    hospital, doctor_entry, err = _require_doctor(request)
    if err:
        return err

    if doctor_entry:
        appt = get_object_or_404(Appointment, id=appointment_id, doctor=doctor_entry)
    else:
        appt = get_object_or_404(Appointment, id=appointment_id, hospital=hospital)
    new_status = request.data.get('status', '')
    if new_status not in ('confirmed', 'cancelled', 'completed'):
        return Response({'error': 'Недопустимый статус'}, status=400)

    appt.status = new_status
    appt.save(update_fields=['status', 'updated_at'])
    return Response({'ok': True, 'id': appt.id, 'status': appt.status})


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def doctor_update_recommendation(request, appointment_id):
    """
    PATCH /api/doctor/appointments/<id>/recommendation/
    Body: {"doctor_recommendation": "Что взять, как лечиться дальше"}
    """
    hospital, doctor_entry, err = _require_doctor(request)
    if err:
        return err

    if doctor_entry:
        appt = get_object_or_404(Appointment, id=appointment_id, doctor=doctor_entry)
    else:
        appt = get_object_or_404(Appointment, id=appointment_id, hospital=hospital)

    recommendation = (request.data.get('doctor_recommendation') or '').strip()
    appt.doctor_recommendation = recommendation
    appt.save(update_fields=['doctor_recommendation', 'updated_at'])
    return Response({'ok': True, 'id': appt.id, 'doctor_recommendation': appt.doctor_recommendation})


# ═══════════════════════════════════════════════════════════════
#  ADMIN API
# ═══════════════════════════════════════════════════════════════

def _require_admin(request):
    """Возвращает ошибку если пользователь не администратор."""
    if not request.user.is_authenticated:
        return None, Response({'error': 'Требуется авторизация'}, status=401)
    profile = getattr(request.user, 'profile', None)
    is_admin = (profile and profile.role == 'admin') or request.user.is_staff
    if not is_admin:
        return None, Response({'error': 'Нет прав администратора'}, status=403)
    return request.user, None


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_stats(request):
    """GET /api/admin/stats/ — общая статистика системы."""
    _, err = _require_admin(request)
    if err:
        return err

    return Response({
        'hospitals':    Hospital.objects.count(),
        'doctors':      Doctor.objects.filter(is_active=True).count(),
        'users':        User.objects.filter(profile__role='patient').count(),
        'appointments': Appointment.objects.count(),
        'confirmed':    Appointment.objects.filter(status='confirmed').count(),
        'invite_codes': DoctorInviteCode.objects.filter(is_used=False).count(),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_hospitals(request):
    """GET /api/admin/hospitals/ — список больниц с числом врачей."""
    _, err = _require_admin(request)
    if err:
        return err

    data = []
    for h in Hospital.objects.all():
        data.append({
            'id':           h.id,
            'name':         h.name,
            'type':         h.type,
            'address':      h.address,
            'doctor_count': h.doctors.filter(is_active=True).count(),
        })
    return Response(data)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def admin_doctors(request):
    """
    GET  /api/admin/doctors/  — все врачи
    POST /api/admin/doctors/  — создать врача
      Body: {hospital_id, full_name, specialty, cabinet, work_days, work_hours}
    """
    _, err = _require_admin(request)
    if err:
        return err

    if request.method == 'GET':
        qs = Doctor.objects.select_related('hospital', 'user').all()
        data = [{
            'id':         d.id,
            'full_name':  d.full_name,
            'specialty':  d.specialty,
            'cabinet':    d.cabinet,
            'work_days':  d.work_days,
            'work_hours': d.work_hours,
            'is_active':  d.is_active,
            'hospital':   {'id': d.hospital.id, 'name': d.hospital.name},
            'user_id':    d.user_id,
            'username':   d.user.username if d.user else None,
        } for d in qs]
        return Response(data)

    # POST — создать врача
    hid = request.data.get('hospital_id')
    full_name = (request.data.get('full_name') or '').strip()
    specialty = (request.data.get('specialty') or '').strip()
    if not hid or not full_name or not specialty:
        return Response({'error': 'Укажите hospital_id, full_name и specialty'}, status=400)

    valid_specs = [s[0] for s in SPECIALTIES_CHOICES]
    if specialty not in valid_specs:
        return Response({'error': f'Недопустимая специальность. Варианты: {", ".join(valid_specs)}'}, status=400)

    hospital = get_object_or_404(Hospital, pk=hid)
    doctor = Doctor.objects.create(
        hospital=hospital,
        full_name=full_name,
        specialty=specialty,
        cabinet=request.data.get('cabinet', ''),
        work_days=request.data.get('work_days', 'Пн-Пт'),
        work_hours=request.data.get('work_hours', '08:00-18:00'),
        is_active=True,
    )
    return Response({
        'ok':       True,
        'id':       doctor.id,
        'full_name': doctor.full_name,
        'specialty': doctor.specialty,
        'hospital': doctor.hospital.name,
    }, status=201)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def admin_doctor_detail(request, doctor_id):
    """
    PATCH  /api/admin/doctors/<id>/  — обновить врача
    DELETE /api/admin/doctors/<id>/  — удалить врача
    """
    _, err = _require_admin(request)
    if err:
        return err

    doctor = get_object_or_404(Doctor, pk=doctor_id)

    if request.method == 'DELETE':
        doctor.delete()
        return Response({'ok': True})

    # PATCH
    for field in ('full_name', 'specialty', 'cabinet', 'work_days', 'work_hours', 'is_active'):
        if field in request.data:
            setattr(doctor, field, request.data[field])
    if 'hospital_id' in request.data:
        doctor.hospital = get_object_or_404(Hospital, pk=request.data['hospital_id'])
    doctor.save()
    return Response({'ok': True, 'id': doctor.id, 'full_name': doctor.full_name})


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def admin_invite_codes(request):
    """
    GET  /api/admin/invite-codes/ — все коды приглашений
    POST /api/admin/invite-codes/ — сгенерировать новый код
      Body: {hospital_id, specialty}
    """
    _, err = _require_admin(request)
    if err:
        return err

    if request.method == 'GET':
        qs = DoctorInviteCode.objects.select_related('hospital', 'used_by').all()
        data = [{
            'id':        c.id,
            'code':      c.code,
            'specialty': c.specialty,
            'is_used':   c.is_used,
            'used_by':   c.used_by.get_full_name() or c.used_by.email if c.used_by else None,
            'hospital':  {'id': c.hospital.id, 'name': c.hospital.name} if c.hospital else None,
            'created_at': c.created_at.strftime('%d.%m.%Y %H:%M'),
        } for c in qs]
        return Response(data)

    # POST — создать код
    hid       = request.data.get('hospital_id')
    specialty = (request.data.get('specialty') or '').strip()
    hospital  = get_object_or_404(Hospital, pk=hid) if hid else None

    code = DoctorInviteCode.objects.create(
        code=DoctorInviteCode.generate_code(),
        hospital=hospital,
        specialty=specialty,
    )
    return Response({
        'ok':        True,
        'id':        code.id,
        'code':      code.code,
        'specialty': code.specialty,
        'hospital':  code.hospital.name if code.hospital else None,
    }, status=201)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def admin_invite_code_detail(request, code_id):
    """DELETE /api/admin/invite-codes/<id>/ — отозвать код (только неиспользованные)."""
    _, err = _require_admin(request)
    if err:
        return err

    code = get_object_or_404(DoctorInviteCode, pk=code_id)
    if code.is_used:
        return Response({'error': 'Нельзя удалить уже использованный код'}, status=400)
    code.delete()
    return Response({'ok': True})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_users(request):
    """GET /api/admin/users/ — список всех пользователей."""
    _, err = _require_admin(request)
    if err:
        return err

    users = User.objects.select_related('profile').all().order_by('-date_joined')
    data = [{
        'id':         u.id,
        'name':       u.get_full_name() or u.first_name or u.username,
        'email':      u.email,
        'role':       getattr(u, 'profile', None) and u.profile.role or 'patient',
        'joined':     u.date_joined.strftime('%d.%m.%Y'),
        'is_active':  u.is_active,
    } for u in users]
    return Response(data)
