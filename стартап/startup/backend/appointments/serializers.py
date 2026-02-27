from rest_framework import serializers
from .models import Hospital, Appointment, Doctor


class DoctorSerializer(serializers.ModelSerializer):
    """Сериализатор для врачей"""
    current_queue = serializers.ReadOnlyField()

    class Meta:
        model = Doctor
        fields = [
            'id',
            'full_name',
            'specialty',
            'cabinet',
            'work_days',
            'work_hours',
            'current_queue',
            'is_active',
        ]


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
            'doctor',
            'specialty',
            'datetime'
        ]
        extra_kwargs = {
            'doctor': {'required': False, 'allow_null': True},
        }

    def validate(self, data):
        from django.utils import timezone
        if data['datetime'] < timezone.now():
            raise serializers.ValidationError({'datetime': 'Нельзя записаться на прошедшее время'})
        doctor = data.get('doctor')
        if doctor:
            if doctor.hospital_id != data['hospital'].id:
                raise serializers.ValidationError({'doctor': 'Этот врач не работает в выбранной больнице'})
            # Синхронизируем специальность из врача
            data['specialty'] = doctor.specialty
        return data


class AppointmentStatusSerializer(serializers.ModelSerializer):
    """Детальная информация о записи для проверки статуса"""
    hospital_name = serializers.CharField(source='hospital.name', read_only=True)
    hospital_address = serializers.CharField(source='hospital.address', read_only=True)
    hospital_type = serializers.CharField(source='hospital.type', read_only=True)
    doctor_name = serializers.CharField(source='doctor.full_name', read_only=True, default=None)
    doctor_cabinet = serializers.CharField(source='doctor.cabinet', read_only=True, default=None)
    estimated_wait_time = serializers.ReadOnlyField()

    class Meta:
        model = Appointment
        fields = [
            'code',
            'patient_name',
            'hospital_name',
            'hospital_address',
            'hospital_type',
            'doctor_name',
            'doctor_cabinet',
            'specialty',
            'datetime',
            'queue_position',
            'estimated_wait_time',
            'status',
            'created_at'
        ]