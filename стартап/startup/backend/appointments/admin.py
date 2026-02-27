from django.contrib import admin
from .models import Hospital, Appointment, VerificationCode, Doctor


@admin.register(Hospital)
class HospitalAdmin(admin.ModelAdmin):
    """Админка для больниц"""
    list_display = ['name', 'type', 'address', 'waiting_time', 'current_queue', 'is_active']
    list_filter = ['type', 'is_active']
    search_fields = ['name', 'address']
    list_editable = ['is_active', 'waiting_time']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'type', 'address')
        }),
        ('Настройки', {
            'fields': ('waiting_time', 'is_active')
        }),
    )


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    """Админка для записей"""
    list_display = [
        'code', 
        'patient_name', 
        'hospital', 
        'specialty', 
        'datetime',
        'queue_position',
        'status',
        'created_at'
    ]
    list_filter = ['status', 'specialty', 'hospital', 'created_at']
    search_fields = ['code', 'patient_name', 'hospital__name']
    readonly_fields = ['code', 'created_at', 'updated_at', 'estimated_wait_time']
    
    fieldsets = (
        ('Информация о записи', {
            'fields': ('code', 'patient_name', 'hospital', 'specialty')
        }),
        ('Дата и время', {
            'fields': ('datetime', 'queue_position', 'estimated_wait_time')
        }),
        ('Статус', {
            'fields': ('status',)
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['mark_as_completed', 'mark_as_cancelled']
    
    def mark_as_completed(self, request, queryset):
        """Отметить записи как завершённые"""
        updated = queryset.update(status='completed')
        self.message_user(request, f'Отмечено как завершённые: {updated} записей')
    mark_as_completed.short_description = "Отметить как завершённые"
    
    def mark_as_cancelled(self, request, queryset):
        """Отменить записи"""
        updated = queryset.update(status='cancelled')
        self.message_user(request, f'Отменено: {updated} записей')
    mark_as_cancelled.short_description = "Отменить записи"


@admin.register(VerificationCode)
class VerificationCodeAdmin(admin.ModelAdmin):
    """Админка для кодов верификации"""
    list_display = ['email', 'code', 'name', 'created_at']
    readonly_fields = ['created_at']
    search_fields = ['email', 'name']


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    """Админка для врачей"""
    list_display = ['full_name', 'specialty', 'hospital', 'cabinet', 'work_days', 'work_hours', 'current_queue', 'is_active']
    list_filter = ['specialty', 'hospital', 'is_active']
    search_fields = ['full_name', 'hospital__name']
    list_editable = ['is_active', 'cabinet']
    fieldsets = (
        ('Основная информация', {
            'fields': ('hospital', 'full_name', 'specialty', 'cabinet')
        }),
        ('Расписание', {
            'fields': ('work_days', 'work_hours', 'is_active')
        }),
    )