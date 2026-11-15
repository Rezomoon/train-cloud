from django.db import models

from apps.infrastructure.models import AuditModel


class PaymentMethodChoices(models.TextChoices):
    WALLET = "wallet", "Wallet"
    BANK = "bank", "Bank"


class PaymentStatusChoices(models.TextChoices):
    PENDING = "pending", "Pending"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class OrderStatusChoices(models.TextChoices):
    PENDING_PAYMENT = "pending_payment", "Pending Payment"
    PAID = "paid", "Paid"
    PROVISIONING = "provisioning", "Provisioning"
    ACTIVE = "active", "Active"
    CANCELLED = "cancelled", "Cancelled"
    FAILED = "failed", "Failed"


class Order(AuditModel):
    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="orders",
    )
    plan = models.ForeignKey("vps.Plan", on_delete=models.PROTECT)
    duration = models.ForeignKey("vps.Duration", on_delete=models.PROTECT)
    operating_system = models.ForeignKey(
        "infrastructure.OperatingSystem",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    vps = models.OneToOneField(
        "vps.VPS",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order",
    )

    # Purchase snapshot (immutable historical record)
    vps_name = models.CharField(max_length=100, default="My VPS")
    cpu_snapshot = models.IntegerField()
    ram_snapshot = models.IntegerField()
    storage_snapshot = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    # Consolidated payment & lifecycle fields
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(
        max_length=50,
        choices=PaymentMethodChoices.choices,
        default=PaymentMethodChoices.BANK,
    )
    payment_status = models.CharField(
        max_length=50,
        choices=PaymentStatusChoices.choices,
        default=PaymentStatusChoices.PENDING,
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=50,
        choices=OrderStatusChoices.choices,
        default=OrderStatusChoices.PENDING_PAYMENT,
    )

    def __str__(self):
        return f"Order {self.uuid} for User {self.user_id}"
