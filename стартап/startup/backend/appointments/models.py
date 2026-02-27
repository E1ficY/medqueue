from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import random
import string


class Hospital(models.Model):
    """Модель больницы/поликлиники"""
    
    HOSPITAL_TYPES = [
        ('Поликлиника', 'Поликлиника'),
        ('Больница', 'Больница'),
        ('Детская', 'Детская'),
        ('Спец. клиника', 'Спец. клиника'),
    ]
    
    name = models.CharField(max_length=200, verbose_name="Название")
    type = models.CharField(max_length=50, choices=HOSPITAL_TYPES, verbose_name="Тип")
    address = models.CharField(max_length=300, verbose_name="Адрес")
    waiting_time = models.IntegerField(default=10, verbose_name="Среднее ожидание (мин)")
    is_active = models.BooleanField(default=True, verbose_name="Активна")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Больница"
        verbose_name_plural = "Больницы"
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    @property
    def current_queue(self):
        """Количество людей в очереди сейчас"""
        return self.appointments.filter(
            status='confirmed',
            datetime__gte=timezone.now()
        ).count()


SPECIALTIES_CHOICES = [
    ('Терапевт', 'Терапевт'),
    ('Хирург', 'Хирург'),
    ('Стоматолог', 'Стоматолог'),
    ('Педиатр', 'Педиатр'),
    ('Кардиолог', 'Кардиолог'),
    ('Невролог', 'Невролог'),
    ('Офтальмолог', 'Офтальмолог'),
    ('Дерматолог', 'Дерматолог'),
    ('Эндокринолог', 'Эндокринолог'),
    ('Гинеколог', 'Гинеколог'),
    ('Уролог', 'Уролог'),
    ('Психиатр', 'Психиатр'),
]


class Doctor(models.Model):
    """Модель врача"""
    hospital = models.ForeignKey(
        Hospital,
        on_delete=models.CASCADE,
        related_name='doctors',
        verbose_name="Больница"
    )
    full_name = models.CharField(max_length=200, verbose_name="ФИО врача")
    specialty = models.CharField(max_length=50, choices=SPECIALTIES_CHOICES, verbose_name="Специальность")
    cabinet = models.CharField(max_length=20, blank=True, verbose_name="Кабинет")
    work_days = models.CharField(max_length=100, default="Пн-Пт", verbose_name="Рабочие дни")
    work_hours = models.CharField(max_length=50, default="08:00-18:00", verbose_name="Рабочие часы")
    is_active = models.BooleanField(default=True, verbose_name="Активен")

    class Meta:
        verbose_name = "Врач"
        verbose_name_plural = "Врачи"
        ordering = ['specialty', 'full_name']

    def __str__(self):
        return f"{self.full_name} ({self.specialty}) — {self.hospital.name}"

    @property
    def current_queue(self):
        """Количество человек в очереди к этому врачу сейчас"""
        return self.appointments.filter(
            status='confirmed',
            datetime__gte=timezone.now()
        ).count()


class Appointment(models.Model):
    """Модель записи на приём"""

    SPECIALTIES = SPECIALTIES_CHOICES
    
    STATUS_CHOICES = [
        ('confirmed', 'Подтверждена'),
        ('cancelled', 'Отменена'),
        ('completed', 'Завершена'),
    ]
    
    code = models.CharField(max_length=6, unique=True, editable=False, verbose_name="Код записи")
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appointments',
        verbose_name="Пользователь"
    )
    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appointments',
        verbose_name="Врач"
    )
    patient_name = models.CharField(max_length=200, verbose_name="Имя пациента")
    hospital = models.ForeignKey(
        Hospital, 
        on_delete=models.CASCADE, 
        related_name='appointments',
        verbose_name="Больница"
    )
    specialty = models.CharField(max_length=50, choices=SPECIALTIES, verbose_name="Специальность")
    datetime = models.DateTimeField(verbose_name="Дата и время приёма")
    queue_position = models.IntegerField(default=1, verbose_name="Место в очереди")
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='confirmed',
        verbose_name="Статус"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Запись"
        verbose_name_plural = "Записи"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.code} - {self.patient_name} ({self.hospital.name})"
    
    def save(self, *args, **kwargs):
        # Генерируем уникальный код при создании
        if not self.code:
            self.code = self.generate_unique_code()
        
        # Автоматически присваиваем место в очереди
        if not self.queue_position or self.queue_position == 1:
            same_day_appointments = Appointment.objects.filter(
                hospital=self.hospital,
                datetime__date=self.datetime.date(),
                status='confirmed'
            ).exclude(pk=self.pk).count()
            self.queue_position = same_day_appointments + 1
        
        super().save(*args, **kwargs)
    
    @staticmethod
    def generate_unique_code():
        """Генерирует уникальный 6-значный код"""
        chars = string.ascii_uppercase + string.digits
        chars = chars.replace('O', '').replace('0', '').replace('I', '').replace('1', '')
        
        while True:
            code = ''.join(random.choices(chars, k=6))
            if not Appointment.objects.filter(code=code).exists():
                return code
    
    @property
    def estimated_wait_time(self):
        """Примерное время ожидания в минутах"""
        return self.queue_position * 5


class VerificationCode(models.Model):
    """Коды подтверждения email при регистрации"""
    email = models.EmailField(verbose_name="Email")
    code = models.CharField(max_length=6, verbose_name="Код")
    name = models.CharField(max_length=200, verbose_name="Имя")
    password = models.CharField(max_length=200, verbose_name="Пароль")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Код верификации"
        verbose_name_plural = "Коды верификации"

    def is_expired(self):
        """Истёк ли код (10 минут)"""
        return (timezone.now() - self.created_at).total_seconds() > 600

    def __str__(self):
        return f"{self.email} — {self.code}"