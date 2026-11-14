from django.db import models
from apps.infrastructure.models import AuditModel
# Create your models here.

class Order(AuditModel):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)
    vps = models.ForeignKey('vps.VPS', on_delete=models.CASCADE)
    status = models.CharField(max_length=50, choices=[('pending', 'Pending'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], default='pending')
    transaction = models.OneToOneField('Transaction', on_delete=models.CASCADE, null=True, blank=True)
    def __str__(self):
        return f"Order {self.id} for User {self.user.id}"

class Transaction(AuditModel):
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=50, choices=[('wallet', 'Wallet'),  ('bank', 'Bank')], default='bank')
    status = models.CharField(max_length=50, choices=[('pending', 'Pending'), ('completed', 'Completed'), ('failed', 'Failed')], default='pending')
