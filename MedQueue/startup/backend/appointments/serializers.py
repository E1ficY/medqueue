from rest_framework import serializers
from django.utils import timezone
from .models import Hospital, Appointment, Doctor


class DoctorSerializer(serializers.ModelSerializer):
    """Сериализатор для врача (используется в карточке больницы и при выборе)"""
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
    """Краткий сериализатор для списка больниц"""
    current_queue = serializers.ReadOnlyField()

    class Meta:
        model = Hospital
        fields = [
            'id',
            'name',
            'type',
            'address',
            'phone',
            'waiting_time',
            'current_queue',
            'latitude',
            'longitude',
            'is_active',
        ]


class HospitalDetailSerializer(serializers.ModelSerializer):
    """Детальный сериализатор — включает описание и список врачей (для страницы больницы)"""
    current_queue = serializers.ReadOnlyField()
    doctors       = DoctorSerializer(many=True, read_only=True)

    class Meta:
        model = Hospital
        fields = [
            'id',
            'name',
            'type',
            'address',
            'phone',
            'description',
            'waiting_time',
            'current_queue',
            'latitude',
            'longitude',
            'doctors',
            'is_active',
        ]


class AppointmentCreateSerializer(serializers.ModelSerializer):
    """Сериализатор для создания новой записи"""

    class Meta:
        model = Appointment
        fields = [
            'patient_name',
            'hospital',
            'doctor',
            'specialty',
            'datetime',
        ]
        extra_kwargs = {
            'doctor': {'required': False, 'allow_null': True},
        }

    def validate(self, data):
        # Запрещаем записываться в прошлое
        if data['datetime'] < timezone.now():
            raise serializers.ValidationError(
                {'datetime': 'Нельзя записаться на прошедшее время'}
            )
        doctor = data.get('doctor')
        if doctor:
            # Врач должен принадлежать выбранной больнице
            if doctor.hospital_id != data['hospital'].id:
                raise serializers.ValidationError(
                    {'doctor': 'Этот врач не работает в выбранной больнице'}
                )
            # Автоматически берём специальность от врача
            data['specialty'] = doctor.specialty
        return data


class AppointmentStatusSerializer(serializers.ModelSerializer):
    """Детальный сериализатор для проверки статуса записи"""
    hospital_name    = serializers.CharField(source='hospital.name',    read_only=True)
    hospital_address = serializers.CharField(source='hospital.address', read_only=True)
    hospital_type    = serializers.CharField(source='hospital.type',    read_only=True)
    doctor_name      = serializers.CharField(source='doctor.full_name', read_only=True, default=None)
    doctor_cabinet   = serializers.CharField(source='doctor.cabinet',   read_only=True, default=None)
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
            'created_at',
        ]