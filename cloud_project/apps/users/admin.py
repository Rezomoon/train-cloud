from django.contrib import admin
from .models import User
# Register your models here.


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('id', 'email', 'mobile', 'role', 'is_staff', 'is_superuser', 'is_active', 'created_at', 'updated_at')
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active')
    search_fields = ('email', 'mobile')
    ordering = ('id',)
