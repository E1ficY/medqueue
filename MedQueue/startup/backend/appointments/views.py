from collections import defaultdict
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.contrib.auth.models import User
from .models import Hospital, Appointment, Doctor, DoctorInviteCode, UserProfile, SPECIALTIES_CHOICES
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
#  DOCTOR PORTAL  —  /api/doctor/...
# ─────────────────────────────────────────────

def _require_doctor(request):
    """Returns (hospital, error_response). If error_response is not None — return it."""
    if not request.user.is_authenticated:
        return None, Response({'error': 'Требуется авторизация'}, status=401)
    try:
        invite = request.user.doctor_invite  # OneToOne from DoctorInviteCode
    except Exception:
        return None, Response({'error': 'Аккаунт врача не найден'}, status=403)
    if not invite.hospital:
        return None, Response({'error': 'Больница не привязана к вашему аккаунту'}, status=403)
    return invite.hospital, None


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def doctor_me(request):
    """
    GET /api/doctor/me/
    Возвращает профиль врача: имя, email, больница, специальность.
    """
    hospital, err = _require_doctor(request)
    if err:
        return err

    invite = request.user.doctor_invite
    today = timezone.now().date()

    today_count = Appointment.objects.filter(
        hospital=hospital,
        datetime__date=today,
        status='confirmed'
    ).count()

    total_count = Appointment.objects.filter(hospital=hospital).count()

    return Response({
        'name': request.user.get_full_name() or request.user.first_name or request.user.username,
        'email': request.user.email,
        'specialty': invite.specialty or 'Не указана',
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
    Записи пациентов в больнице врача.
    """
    hospital, err = _require_doctor(request)
    if err:
        return err

    invite = request.user.doctor_invite
    qs = Appointment.objects.filter(hospital=hospital).order_by('datetime')

    # Фильтр по специальности врача (если задана)
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
        })

    return Response(data)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def doctor_update_appointment(request, appointment_id):
    """
    PATCH /api/doctor/appointments/<id>/
    Body: {"status": "completed" | "cancelled" | "confirmed"}
    Врач может менять статус только записей своей больницы.
    """
    hospital, err = _require_doctor(request)
    if err:
        return err

    appt = get_object_or_404(Appointment, id=appointment_id, hospital=hospital)
    new_status = request.data.get('status', '')
    if new_status not in ('confirmed', 'cancelled', 'completed'):
        return Response({'error': 'Недопустимый статус'}, status=400)

    appt.status = new_status
    appt.save(update_fields=['status', 'updated_at'])
    return Response({'ok': True, 'id': appt.id, 'status': appt.status})


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
        qs = Doctor.objects.select_related('hospital').all()
        data = [{
            'id':         d.id,
            'full_name':  d.full_name,
            'specialty':  d.specialty,
            'cabinet':    d.cabinet,
            'work_days':  d.work_days,
            'work_hours': d.work_hours,
            'is_active':  d.is_active,
            'hospital':   {'id': d.hospital.id, 'name': d.hospital.name},
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
