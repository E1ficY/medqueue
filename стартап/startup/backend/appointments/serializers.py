from rest_framework import serializers
from .models import Hospital, Appointment


class HospitalSerializer(serializers.ModelSerializer):
    """Сериализатор для больниц"""
    current_queue = serializers.ReadOnlyField()
    
    class Meta:
        model = Hospital
        fields = [
            'id', 
            'name', 
            'type', 
            'address', 
            'waiting_time',
            'current_queue',
            'is_active'
        ]


class AppointmentSerializer(serializers.ModelSerializer):
    """Сериализатор для записей"""
    hospital_name = serializers.CharField(source='hospital.name', read_only=True)
    hospital_address = serializers.CharField(source='hospital.address', read_only=True)
    estimated_wait_time = serializers.ReadOnlyField()
    code = serializers.CharField(read_only=True)
    
    class Meta:
        model = Appointment
        fields = [
            'id',
            'code',
            'patient_name',
            'hospital',
            'hospital_name',
            'hospital_address',
            'specialty',
            'datetime',
            'queue_position',
            'status',
            'estimated_wait_time',
            'created_at'
        ]
        read_only_fields = ['code', 'queue_position', 'created_at']
    
    def validate_datetime(self, value):
        """Проверка что дата в будущем"""
        from django.utils import timezone
        if value < timezone.now():
            raise serializers.ValidationError("Нельзя записаться на прошедшее время")
        return value


class AppointmentCreateSerializer(serializers.ModelSerializer):
    """Упрощенный сериализатор для создания записи"""
    
    class Meta:
        model = Appointment
        fields = [
            'patient_name',
            'hospital',
            'specialty',
            'datetime'
        ]
    
    def validate_datetime(self, value):
        from django.utils import timezone
        if value < timezone.now():
            raise serializers.ValidationError("Нельзя записаться на прошедшее время")
        return value


class AppointmentStatusSerializer(serializers.ModelSerializer):
    """Детальная информация о записи для проверки статуса"""
    hospital_name = serializers.CharField(source='hospital.name', read_only=True)
    hospital_address = serializers.CharField(source='hospital.address', read_only=True)
    hospital_type = serializers.CharField(source='hospital.type', read_only=True)
    estimated_wait_time = serializers.ReadOnlyField()
    
    class Meta:
        model = Appointment
        fields = [
            'code',
            'patient_name',
            'hospital_name',
            'hospital_address',
            'hospital_type',
            'specialty',
            'datetime',
            'queue_position',
            'estimated_wait_time',
            'status',
            'created_at'
        ]