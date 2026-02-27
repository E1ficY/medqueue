from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Hospital, Appointment
from .serializers import (
    HospitalSerializer, 
    AppointmentSerializer,
    AppointmentCreateSerializer,
    AppointmentStatusSerializer
)


class HospitalViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API для больниц
    
    GET /api/hospitals/ - список всех больниц
    GET /api/hospitals/{id}/ - детали одной больницы
    """
    queryset = Hospital.objects.filter(is_active=True)
    serializer_class = HospitalSerializer
    
    def list(self, request):
        """Получить список всех активных больниц"""
        hospitals = self.get_queryset()
        serializer = self.get_serializer(hospitals, many=True)
        return Response(serializer.data)


class AppointmentViewSet(viewsets.ModelViewSet):
    """
    API для записей
    
    POST /api/appointments/ - создать новую запись
    GET /api/appointments/check/{code}/ - проверить статус по коду
    DELETE /api/appointments/{code}/cancel/ - отменить запись
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
        appointment = serializer.save()
        
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
        
        return Response({
            'message': 'Запись успешно отменена',
            'code': code
        })
    
    @action(detail=False, methods=['get'])
    def my_appointments(self, request):
        """
        Получить все записи (для админки или личного кабинета)
        
        GET /api/appointments/my_appointments/
        """
        appointments = Appointment.objects.filter(status='confirmed')
        serializer = AppointmentStatusSerializer(appointments, many=True)
        return Response(serializer.data)