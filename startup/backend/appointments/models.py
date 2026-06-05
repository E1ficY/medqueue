from django.db import models
from django.db.models import Avg, Count
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from statistics import median
import random
import string


UNIFORM_MINUTES_PER_PATIENT = 15


class Hospital(models.Model):
    """Модель больницы/поликлиники"""

    HOSPITAL_TYPES = [
        ('Поликлиника', 'Поликлиника'),
        ('Больница', 'Больница'),
        ('Детская', 'Детская'),
        ('Спец. клиника', 'Спец. клиника'),
    ]

    name         = models.CharField(max_length=200, verbose_name="Название")
    type         = models.CharField(max_length=50, choices=HOSPITAL_TYPES, verbose_name="Тип")
    address      = models.CharField(max_length=300, verbose_name="Адрес")
    phone        = models.CharField(max_length=50, blank=True, default='', verbose_name="Телефон")
    description  = models.TextField(blank=True, default='', verbose_name="Описание")
    latitude     = models.FloatField(null=True, blank=True, verbose_name="Широта")
    longitude    = models.FloatField(null=True, blank=True, verbose_name="Долгота")
    waiting_time = models.IntegerField(default=10, verbose_name="Среднее ожидание (мин)")
    is_active    = models.BooleanField(default=True, verbose_name="Активна")
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Больница"
        verbose_name_plural = "Больницы"
        ordering = ['name']
        indexes = [
            models.Index(fields=['is_active'], name='hospital_is_active_idx'),
            models.Index(fields=['is_active', 'name'], name='hospital_active_name_idx'),
        ]

    def __str__(self):
        return self.name

    @property
    def current_queue(self):
        """Количество людей в очереди прямо сейчас"""
        return self.appointments.filter(
            status='confirmed',
            datetime__gte=timezone.now()
        ).count()

    @property
    def estimated_waiting_time(self):
        """Единый расчет ожидания для всех больниц."""
        queue_count = self.current_queue
        if queue_count <= 0:
            return 0
        return queue_count * UNIFORM_MINUTES_PER_PATIENT

    @property
    def waiting_time_reason(self):
        queue_count = self.current_queue
        if queue_count <= 0:
            return 'Ожидание 0 минут, потому что в очереди сейчас нет пациентов.'
        return (
            f'Расчет: {queue_count} чел. x {UNIFORM_MINUTES_PER_PATIENT} мин = '
            f'{self.estimated_waiting_time} мин.'
        )

    @property
    def reviews_count(self):
        return DoctorReview.objects.filter(
            doctor__hospital=self,
            doctor__is_active=True,
        ).count()

    @property
    def avg_rating(self):
        result = DoctorReview.objects.filter(
            doctor__hospital=self,
            doctor__is_active=True,
        ).aggregate(avg=Avg('rating'))
        value = result.get('avg')
        if value is None:
            return 0.0
        return round(float(value), 1)


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
    user = models.OneToOneField(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='doctor_profile',
        verbose_name="Аккаунт пользователя"
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
        indexes = [
            models.Index(fields=['hospital', 'is_active'], name='doctor_hospital_active_idx'),
            models.Index(fields=['specialty', 'is_active'], name='doctor_specialty_active_idx'),
            models.Index(fields=['is_active'], name='doctor_is_active_idx'),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.specialty}) — {self.hospital.name}"

    @property
    def reviews_count(self):
        return self.reviews.count()

    @property
    def avg_rating(self):
        reviews = self.reviews.all()
        if not reviews:
            return 0.0
        total = sum(item.rating for item in reviews)
        return round(total / reviews.count(), 1)

    @property
    def current_queue(self):
        """Количество человек в очереди к этому врачу сейчас"""
        return self.appointments.filter(
            status='confirmed',
            datetime__gte=timezone.now()
        ).count()

    def _historical_service_minutes(self):
        """
        Оценка средней длительности обслуживания на основе интервалов
        между завершенными приемами (по расписанию).
        """
        completed = list(
            self.appointments.filter(status='completed')
            .order_by('-datetime')
            .values_list('datetime', flat=True)[:36]
        )
        if len(completed) < 3:
            return UNIFORM_MINUTES_PER_PATIENT, 0

        completed = sorted(completed)
        gaps = []
        for i in range(1, len(completed)):
            diff = int((completed[i] - completed[i - 1]).total_seconds() // 60)
            if 5 <= diff <= 90:
                gaps.append(diff)

        if not gaps:
            return UNIFORM_MINUTES_PER_PATIENT, 0

        return int(round(median(gaps))), len(gaps)

    @property
    def wait_forecast_minutes(self):
        """Прогноз времени до приема у врача в минутах."""
        queue_now = self.current_queue
        if queue_now <= 0:
            return 0

        base_minutes, sample_size = self._historical_service_minutes()
        now = timezone.localtime()

        # Небольшая поправка на загруженные часы/дни.
        hour_factor = 1.15 if 10 <= now.hour <= 13 else (0.92 if now.hour >= 17 else 1.0)
        day_factor = 1.1 if now.weekday() in (0, 4) else 1.0  # пн/пт обычно плотнее
        sample_factor = 0.95 if sample_size >= 12 else 1.0

        eta = int(round(queue_now * base_minutes * hour_factor * day_factor * sample_factor))
        return max(0, min(180, eta))

    @property
    def wait_forecast_confidence(self):
        """Оценка уверенности прогноза в процентах."""
        _, sample_size = self._historical_service_minutes()
        if sample_size <= 0:
            return 48
        return max(55, min(93, 55 + sample_size))

    @property
    def wait_forecast_reason(self):
        queue_now = self.current_queue
        base_minutes, sample_size = self._historical_service_minutes()
        if queue_now <= 0:
            return 'Свободное окно: сейчас перед вами нет пациентов.'
        source = 'история приемов врача' if sample_size > 0 else 'базовый шаг системы'
        return (
            f'Прогноз: {queue_now} в очереди x ~{base_minutes} мин, источник: {source}, '
            f'точность {self.wait_forecast_confidence}%.'
        )


class Appointment(models.Model):
    """Модель записи на приём"""

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
    specialty = models.CharField(max_length=50, choices=SPECIALTIES_CHOICES, verbose_name="Специальность")
    datetime = models.DateTimeField(verbose_name="Дата и время приёма")
    queue_position = models.IntegerField(default=1, verbose_name="Место в очереди")
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='confirmed',
        verbose_name="Статус"
    )
    comment = models.TextField(blank=True, default='', verbose_name="Комментарий пациента")
    doctor_recommendation = models.TextField(blank=True, default='', verbose_name="Рекомендации врача")
    exam_summary = models.TextField(blank=True, default='', verbose_name="Итоги обследования")
    prescribed_medications = models.TextField(blank=True, default='', verbose_name="Назначенные препараты")
    prescription_confirmed = models.BooleanField(default=False, verbose_name="Рецепт подтвержден врачом")
    prescription_confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name="Когда подтвержден рецепт")
    prescription_confirmed_by = models.CharField(max_length=200, blank=True, default='', verbose_name="Кем подтвержден рецепт")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Запись"
        verbose_name_plural = "Записи"
        ordering = ['-created_at']
        indexes = [
            # Записи конкретного пользователя — профиль, история
            models.Index(fields=['user', 'status'], name='appt_user_status_idx'),
            models.Index(fields=['user', 'created_at'], name='appt_user_created_idx'),
            # Очередь к врачу — самый частый subquery
            models.Index(fields=['doctor', 'status', 'datetime'], name='appt_doctor_status_dt_idx'),
            # Очередь в больнице
            models.Index(fields=['hospital', 'status', 'datetime'], name='appt_hospital_status_dt_idx'),
            # Поиск по коду записи (уже unique, но явный индекс)
            models.Index(fields=['code'], name='appt_code_idx'),
            # Для admin stats / подсчёта
            models.Index(fields=['status'], name='appt_status_idx'),
            models.Index(fields=['created_at'], name='appt_created_at_idx'),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.patient_name} ({self.hospital.name})"
    
    def save(self, *args, **kwargs):
        # Генерируем уникальный код при создании
        if not self.code:
            self.code = self.generate_unique_code()
        
        # На создании считаем позицию устойчиво по интервалу локального дня.
        if self._state.adding or not self.queue_position:
            from django.db import transaction
            with transaction.atomic():
                if self.hospital_id:
                    Hospital.objects.select_for_update().get(pk=self.hospital_id)
                    
                local_dt = timezone.localtime(self.datetime) if timezone.is_aware(self.datetime) else self.datetime
                day_start = local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = day_start + timedelta(days=1)
    
                if timezone.is_naive(day_start):
                    day_start = timezone.make_aware(day_start, timezone.get_current_timezone())
                    day_end = timezone.make_aware(day_end, timezone.get_current_timezone())
    
                same_day_appointments = Appointment.objects.filter(
                    hospital=self.hospital,
                    status='confirmed',
                    datetime__gte=day_start,
                    datetime__lt=day_end,
                    datetime__lte=self.datetime,
                ).exclude(pk=self.pk).count()
                self.queue_position = same_day_appointments + 1
                super().save(*args, **kwargs)
            return
        
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
        people_ahead = max((self.queue_position or 1) - 1, 0)
        if people_ahead == 0:
            return 0
        return people_ahead * UNIFORM_MINUTES_PER_PATIENT

    @property
    def estimated_wait_reason(self):
        people_ahead = max((self.queue_position or 1) - 1, 0)
        if people_ahead <= 0:
            return 'Ожидание 0 минут, вы первый(ая) в очереди.'
        return (
            f'Перед вами {people_ahead} чел., единый шаг {UNIFORM_MINUTES_PER_PATIENT} мин/чел. '
            f'Итого: {self.estimated_wait_time} мин.'
        )


class DoctorInviteCode(models.Model):
    """
    Коды приглашения для врачей.
    Администратор генерирует код в панели, врач вводит его при регистрации.
    Формат: MEDQ-XXXXXX
    """
    code       = models.CharField(max_length=12, unique=True, verbose_name="Код")
    hospital   = models.ForeignKey(
        Hospital, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='invite_codes',
        verbose_name="Больница"
    )
    specialty  = models.CharField(max_length=50, blank=True, verbose_name="Специальность")
    is_used    = models.BooleanField(default=False, verbose_name="Использован")
    used_by    = models.OneToOneField(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='doctor_invite',
        verbose_name="Врач"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Код приглашения врача"
        verbose_name_plural = "Коды приглашений врачей"
        ordering = ['-created_at']

    def __str__(self):
        if self.is_used and self.used_by:
            status_str = f"✅ {self.used_by.first_name or self.used_by.username}"
        elif self.is_used:
            status_str = "✅ Использован (пользователь удалён)"
        else:
            status_str = "⏳ Свободен"
        return f"{self.code} — {self.specialty or 'Без специальности'} [{status_str}]"

    @classmethod
    def generate_code(cls):
        """Генерирует уникальный код формата MEDQ-XXXXXX"""
        chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # без I, O, 0, 1
        while True:
            code = 'MEDQ-' + ''.join(random.choices(chars, k=6))
            if not cls.objects.filter(code=code).exists():
                return code


class UserProfile(models.Model):
    """Расширенный профиль пользователя — роль системы"""
    ROLES = [
        ('patient', 'Пациент'),
        ('doctor',  'Врач'),
        ('admin',   'Администратор'),
    ]
    user  = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role  = models.CharField(max_length=20, choices=ROLES, default='patient')
    phone = models.CharField(max_length=30, blank=True, default='')

    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"

    def __str__(self):
        return f"{self.user.first_name} ({self.get_role_display()})"

    @property
    def is_doctor(self):
        return self.role == 'doctor'


class PaymentCard(models.Model):
    """Сохранённая карта пациента (храним только безопасные данные)."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='payment_card')
    card_holder = models.CharField(max_length=120, verbose_name="Держатель карты")
    brand = models.CharField(max_length=20, default='VISA', verbose_name="Платежная система")
    last4 = models.CharField(max_length=4, verbose_name="Последние 4 цифры")
    exp_month = models.PositiveSmallIntegerField(verbose_name="Месяц")
    exp_year = models.PositiveSmallIntegerField(verbose_name="Год")
    token = models.CharField(max_length=64, blank=True, default='', verbose_name="Токен")
    is_verified = models.BooleanField(default=False, verbose_name="Подтверждена")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Платёжная карта"
        verbose_name_plural = "Платёжные карты"

    def __str__(self):
        return f"{self.user.username} • {self.brand} ****{self.last4}"


class UserSubscription(models.Model):
    """Подписка пациента."""
    PLAN_CHOICES = [
        ('free', 'Базовая (0 тг)'),
        ('social', 'Льготная Care (0 тг/мес)'),
        ('plus', 'Care Plus (2 990 тг/мес)'),
    ]
    STATUS_CHOICES = [
        ('active', 'Активна'),
        ('cancelled', 'Отменена'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='subscription')
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='free', verbose_name="Тариф")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', verbose_name="Статус")
    auto_taxi_enabled = models.BooleanField(default=False, verbose_name="Авто-заказ такси")
    social_reason = models.TextField(blank=True, default='', verbose_name="Причина льготной подписки")
    social_reason_confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name="Когда подтверждена причина")
    started_at = models.DateTimeField(auto_now_add=True)
    next_billing_date = models.DateField(null=True, blank=True, verbose_name="Следующее списание")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Подписка"
        verbose_name_plural = "Подписки"

    def __str__(self):
        return f"{self.user.username} • {self.get_plan_display()}"


class PaymentTransaction(models.Model):
    """История платежей подписки."""
    STATUS_CHOICES = [
        ('processing', 'Обрабатывается'),
        ('paid', 'Оплачен'),
        ('failed', 'Ошибка'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payment_transactions')
    subscription = models.ForeignKey(
        UserSubscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Сумма")
    currency = models.CharField(max_length=10, default='KZT', verbose_name="Валюта")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='processing', verbose_name="Статус")
    transaction_ref = models.CharField(max_length=32, unique=True, verbose_name="Номер транзакции")
    merchant_name = models.CharField(max_length=120, default='MedQueue Health Services', verbose_name="Мерчант")
    card_last4 = models.CharField(max_length=4, blank=True, default='', verbose_name="Последние 4")
    card_brand = models.CharField(max_length=20, blank=True, default='', verbose_name="Платежная система")
    description = models.CharField(max_length=255, blank=True, default='', verbose_name="Описание")
    authorization_code = models.CharField(max_length=12, blank=True, default='', verbose_name="Код авторизации")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="Оплачено")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Платёж"
        verbose_name_plural = "Платежи"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction_ref} • {self.amount} {self.currency}"


class CardVerificationCode(models.Model):
    """Код подтверждения карты от банка (demo flow)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='card_verification_codes')
    card = models.ForeignKey(PaymentCard, on_delete=models.CASCADE, related_name='verification_codes')
    code = models.CharField(max_length=6, verbose_name="Код")
    is_used = models.BooleanField(default=False, verbose_name="Использован")
    expires_at = models.DateTimeField(verbose_name="Действует до")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Код подтверждения карты"
        verbose_name_plural = "Коды подтверждения карты"
        ordering = ['-created_at']

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"{self.user.username} • {self.code}"


class DoctorReview(models.Model):
    """Отзывы пациентов о враче."""
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='reviews')
    patient_name = models.CharField(max_length=200, verbose_name="Имя пациента")
    rating = models.PositiveSmallIntegerField(verbose_name="Рейтинг")
    comment = models.TextField(blank=True, default='', verbose_name="Комментарий")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Отзыв о враче"
        verbose_name_plural = "Отзывы о врачах"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['doctor', 'created_at'], name='review_doctor_created_idx'),
            models.Index(fields=['doctor'], name='review_doctor_idx'),
        ]

    def __str__(self):
        return f"{self.doctor.full_name} • {self.rating}/5"

    def save(self, *args, **kwargs):
        self.rating = min(max(int(self.rating or 0), 1), 5)
        super().save(*args, **kwargs)


class VerificationCode(models.Model):
    """Коды подтверждения email при регистрации"""
    email       = models.EmailField(verbose_name="Email")
    code        = models.CharField(max_length=6, verbose_name="Код")
    name        = models.CharField(max_length=200, verbose_name="Имя")
    username    = models.CharField(max_length=150, blank=True, default='', verbose_name="Логин")
    password    = models.CharField(max_length=200, verbose_name="Пароль")
    role        = models.CharField(max_length=20, default='patient', verbose_name="Роль")
    doctor_code = models.CharField(max_length=12, blank=True, default='', verbose_name="Код врача")
    phone       = models.CharField(max_length=30, blank=True, default='', verbose_name="Телефон")
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Код верификации"
        verbose_name_plural = "Коды верификации"
        indexes = [
            # Поиск кода при верификации email
            models.Index(fields=['email', 'created_at'], name='vercode_email_created_idx'),
            models.Index(fields=['email'], name='vercode_email_idx'),
        ]

    def is_expired(self):
        """Истёк ли код (10 минут)"""
        return (timezone.now() - self.created_at).total_seconds() > 600

    def __str__(self):
        return f"{self.email} — {self.code}"


class PasswordResetCode(models.Model):
    """Код сброса пароля (отправляется на email, действует 15 минут)"""
    email      = models.EmailField(verbose_name="Email")
    code       = models.CharField(max_length=6, verbose_name="Код")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Код сброса пароля"
        verbose_name_plural = "Коды сброса пароля"
        indexes = [
            # Поиск кода при сбросе пароля
            models.Index(fields=['email', 'created_at'], name='resetcode_email_created_idx'),
            models.Index(fields=['email'], name='resetcode_email_idx'),
        ]

    def is_expired(self):
        return (timezone.now() - self.created_at).total_seconds() > 900  # 15 минут

    def __str__(self):
        return f"{self.email} — {self.code}"