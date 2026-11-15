from django.contrib import admin
from .models import Order

# Register your models here.

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('user', 'status',)
    list_filter = ('status',)
    search_fields = ('user__email', )

