from django.db import models
from apps.infrastructure.models import AuditModel
# Create your models here.

class StatusChoices(models.TextChoices):
    Pending = "pending"
    Completed = "completed"
    Cancelled = "cancelled"
    PendingPayment = "pending_payment"
    Paid = "paid"


class Order(AuditModel):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)
    vps = models.ForeignKey('vps.VPS', null = True, blank=True, on_delete=models.CASCADE)
    status = models.CharField(max_length=50, choices=StatusChoices.choices, default='pending')
    plan = models.ForeignKey('vps.Plan', on_delete=models.CASCADE)
    duration = models.ForeignKey('vps.Duration', on_delete=models.CASCADE)
    resource_price = models.JSONField(null=True, blank=True) # to save the price of the resources at the time of order(snap shot)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=50, choices=[('wallet', 'Wallet'),  ('bank', 'Bank')], default='bank')

    def __str__(self):
        return f"Order {self.uuid} for User {self.user.uuid}"
