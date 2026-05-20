from rest_framework import serializers
from django.utils import timezone
from .models import Hospital, Appointment, Doctor, DoctorReview


class DoctorSerializer(serializers.ModelSerializer):
    """Сериализатор для врача (используется в карточке больницы и при выборе)"""
    current_queue = serializers.ReadOnlyField()
    avg_rating = serializers.ReadOnlyField()
    reviews_count = serializers.ReadOnlyField()
    hospital_id = serializers.IntegerField(source='hospital.id', read_only=True)
    hospital_name = serializers.CharField(source='hospital.name', read_only=True)
    latest_reviews = serializers.SerializerMethodField()
    wait_forecast_minutes = serializers.ReadOnlyField()
    wait_forecast_confidence = serializers.ReadOnlyField()
    wait_forecast_reason = serializers.ReadOnlyField()

    def get_latest_reviews(self, obj):
        reviews = DoctorReview.objects.filter(doctor=obj).order_by('-created_at')[:2]
        return [
            {
                'rating': r.rating,
                'comment': r.comment,
                'patient_name': r.patient_name,
                'created_at': r.created_at.isoformat(),
            }
            for r in reviews
        ]

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
            'avg_rating',
            'reviews_count',
            'hospital_id',
            'hospital_name',
            'latest_reviews',
            'wait_forecast_minutes',
            'wait_forecast_confidence',
            'wait_forecast_reason',
            'is_active',
        ]


class HospitalSerializer(serializers.ModelSerializer):
    """Краткий сериализатор для списка больниц"""
    current_queue = serializers.ReadOnlyField()
    waiting_time = serializers.ReadOnlyField(source='estimated_waiting_time')
    waiting_time_reason = serializers.ReadOnlyField()
    avg_rating = serializers.ReadOnlyField()
    reviews_count = serializers.ReadOnlyField()
    latest_reviews = serializers.SerializerMethodField()

    def get_latest_reviews(self, obj):
        reviews = DoctorReview.objects.filter(
            doctor__hospital=obj,
            doctor__is_active=True,
        ).order_by('-created_at')[:2]
        return [
            {
                'doctor_name': r.doctor.full_name,
                'rating': r.rating,
                'comment': r.comment,
                'patient_name': r.patient_name,
                'created_at': r.created_at.isoformat(),
            }
            for r in reviews
        ]

    class Meta:
        model = Hospital
        fields = [
            'id',
            'name',
            'type',
            'address',
            'phone',
            'waiting_time',
            'waiting_time_reason',
            'avg_rating',
            'reviews_count',
            'latest_reviews',
            'current_queue',
            'latitude',
            'longitude',
            'is_active',
        ]


class HospitalDetailSerializer(serializers.ModelSerializer):
    """Детальный сериализатор — включает описание и список врачей (для страницы больницы)"""
    current_queue = serializers.ReadOnlyField()
    waiting_time = serializers.ReadOnlyField(source='estimated_waiting_time')
    waiting_time_reason = serializers.ReadOnlyField()
    avg_rating = serializers.ReadOnlyField()
    reviews_count = serializers.ReadOnlyField()
    latest_reviews = serializers.SerializerMethodField()
    doctors       = DoctorSerializer(many=True, read_only=True)

    def get_latest_reviews(self, obj):
        reviews = DoctorReview.objects.filter(
            doctor__hospital=obj,
            doctor__is_active=True,
        ).order_by('-created_at')
        return [
            {
                'doctor_name': r.doctor.full_name,
                'rating': r.rating,
                'comment': r.comment,
                'patient_name': r.patient_name,
                'created_at': r.created_at.isoformat(),
            }
            for r in reviews
        ]

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
            'waiting_time_reason',
            'avg_rating',
            'reviews_count',
            'latest_reviews',
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
            'comment',
        ]
        extra_kwargs = {
            'doctor': {'required': False, 'allow_null': True},
            'comment': {'required': False, 'allow_blank': True},
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
    doctor_id        = serializers.IntegerField(source='doctor.id', read_only=True, default=None)
    doctor_name      = serializers.CharField(source='doctor.full_name', read_only=True, default=None)
    doctor_cabinet   = serializers.CharField(source='doctor.cabinet',   read_only=True, default=None)
    estimated_wait_time = serializers.ReadOnlyField()
    estimated_wait_reason = serializers.ReadOnlyField()
    care_plus_support_available = serializers.SerializerMethodField()
    auto_taxi_available = serializers.SerializerMethodField()

    def get_care_plus_support_available(self, obj):
        if not obj.user:
            return False
        sub = getattr(obj.user, 'subscription', None)
        return bool(sub and sub.status == 'active' and sub.plan == 'plus')

    def get_auto_taxi_available(self, obj):
        # Legacy compatibility field for old frontend versions.
        return self.get_care_plus_support_available(obj)

    class Meta:
        model = Appointment
        fields = [
            'code',
            'patient_name',
            'hospital_name',
            'hospital_address',
            'hospital_type',
            'doctor_id',
            'doctor_name',
            'doctor_cabinet',
            'specialty',
            'datetime',
            'queue_position',
            'estimated_wait_time',
            'estimated_wait_reason',
            'status',
            'comment',
            'doctor_recommendation',
            'exam_summary',
            'prescribed_medications',
            'prescription_confirmed',
            'prescription_confirmed_at',
            'prescription_confirmed_by',
            'care_plus_support_available',
            'auto_taxi_available',
            'created_at',
        ]