from django.contrib import admin
from .models import Region, DataCenter, OperatingSystem
# Register your models here.

@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'description') 

@admin.register(DataCenter)
class DataCenterAdmin(admin.ModelAdmin):
    list_display = ('name', 'region', 'is_active')
    list_filter = ('is_active', 'region')
    search_fields = ('name',)

@admin.register(OperatingSystem)
class OperatingSystemAdmin(admin.ModelAdmin):
    list_display = ('name', 'version', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'version')