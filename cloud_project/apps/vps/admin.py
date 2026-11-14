from django.contrib import admin
from .models import Plan, Duration
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