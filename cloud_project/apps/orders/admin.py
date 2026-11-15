from django.contrib import admin
from .models import Order, Transaction

# Register your models here.

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('user', 'status', 'transaction')
    list_filter = ('status',)
    search_fields = ('user__email', 'transaction__uuid')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('amount', 'payment_method', 'status')
    list_filter = ('status', 'payment_method')
    search_fields = ('uuid',)
