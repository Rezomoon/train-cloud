from django.contrib import admin
from .models import Plan, Duration, VPS
# Register your models here.

@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'cpu', 'ram', 'storage', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')


@admin.register(Duration)
class DurationAdmin(admin.ModelAdmin):
    list_display = ('name', 'duration_in_month', 'data_center')
    search_fields = ('name',)

@admin.register(VPS)
class VPSAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'plan',
        'duration',
        'cpu',
        'ram',
        'storage',
        'provider_instance_id',
        'ip_address',
        'status',
    )
    list_filter = ('status',)
    search_fields = (
        'user__email',
        'plan__name',
        'duration__name',
        'ip_address',
        'provider_instance_id',
    )
    readonly_fields = ('cpu', 'ram', 'storage')