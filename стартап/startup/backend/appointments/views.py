from collections import defaultdict
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from .models import Hospital, Appointment, Doctor
from .serializers import (
    HospitalSerializer,
    AppointmentSerializer,
    AppointmentCreateSerializer,
    AppointmentStatusSerializer,
    DoctorSerializer
)


class HospitalViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API для больниц
    
    GET /api/hospitals/ - список всех больниц
    GET /api/hospitals/{id}/ - детали одной больницы
    """
    queryset = Hospital.objects.filter(is_active=True)
    serializer_class = HospitalSerializer

    @action(detail=True, methods=['get'], url_path='doctors')
    def doctors(self, request, pk=None):
        """
        Врачи больницы, сгруппированные по специальностям

        GET /api/hospitals/{id}/doctors/
        Возвращает: [{specialty, doctors: [{id, full_name, cabinet, work_days, work_hours, current_queue}]}]
        """
        hospital = get_object_or_404(Hospital, pk=pk, is_active=True)
        doctors = Doctor.objects.filter(hospital=hospital, is_active=True).order_by('specialty', 'full_name')

        grouped = defaultdict(list)
        for doc in doctors:
            grouped[doc.specialty].append(DoctorSerializer(doc).data)

        result = [
            {'specialty': spec, 'doctors': docs}
            for spec, docs in grouped.items()
        ]
        return Response(result)


class AppointmentViewSet(viewsets.ModelViewSet):
    """
    API для записей

    POST /api/appointments/ - создать новую запись
    GET /api/appointments/check/{code}/ - проверить статус по коду
    POST /api/appointments/cancel/ - отменить запись
    GET /api/appointments/my_appointments/ - записи текущего пользователя
    """
    queryset = Appointment.objects.all()
    serializer_class = AppointmentSerializer
    
    def get_serializer_class(self):
        """Выбираем сериализатор в зависимости от действия"""
        if self.action == 'create':
            return AppointmentCreateSerializer
        elif self.action == 'check_status':
            return AppointmentStatusSerializer
        return AppointmentSerializer
    
    def create(self, request):
        """
        Создать новую запись

        POST /api/appointments/
        Body: {
            "patient_name": "Иван Иванов",
            "hospital": 1,
            "specialty": "Терапевт",
            "datetime": "2025-01-27T10:00:00"
        }
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Привязываем запись к пользователю, если аутентифицирован
        user = request.user if request.user.is_authenticated else None
        appointment = serializer.save(user=user)
        
        # Возвращаем полную информацию о созданной записи
        response_serializer = AppointmentStatusSerializer(appointment)
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=False, methods=['get'], url_path='check/(?P<code>[A-Z0-9]{6})')
    def check_status(self, request, code=None):
        """
        Проверить статус записи по коду
        
        GET /api/appointments/check/{CODE}/
        """
        appointment = get_object_or_404(Appointment, code=code.upper())
        serializer = self.get_serializer(appointment)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'], url_path='cancel')
    def cancel_appointment(self, request):
        """
        Отменить запись
        
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

        # Пересчитываем позиции остальных в очереди в этот день
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
        Записи текущего аутентифицированного пользователя

        GET /api/appointments/my_appointments/
        Требует: Authorization: Bearer <access_token>
        """
        appointments = Appointment.objects.filter(
            user=request.user
        ).order_by('-created_at')
        serializer = AppointmentStatusSerializer(appointments, many=True)
        return Response(serializer.data)