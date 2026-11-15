from django.contrib import admin

from .models import Order


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "uuid",
        "user",
        "vps_name",
        "status",
        "payment_status",
        "total_amount",
        "created_at",
    )
    list_filter = ("status", "payment_status", "payment_method")
    search_fields = ("user__email", "user__mobile", "vps_name")
    readonly_fields = ("uuid", "created_at", "updated_at", "paid_at")
