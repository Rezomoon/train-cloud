from django.db import models
from django.db.models import UniqueConstraint
from django.db.models.functions import Lower
from simple_history.models import HistoricalRecords
from apps.infrastructure.models import AuditModel
# Create your models here.

class Plan(AuditModel):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField()
    cpu = models.IntegerField()
    ram = models.IntegerField()
    storage = models.IntegerField()
    is_active = models.BooleanField(default=True)
    data_center = models.ForeignKey('infrastructure.DataCenter', on_delete=models.CASCADE)
    

    def __str__(self):
        return self.name

class Duration(AuditModel):
    name = models.CharField(max_length=100)
    duration_in_month = models.IntegerField()
    data_center = models.ForeignKey('infrastructure.DataCenter', on_delete=models.CASCADE)

    def __str__(self):
        return self.name

class StatusChoices(models.TextChoices):
    Active = "active"
    Inactive = "inactive"

class VPS(AuditModel):
    # order = models.OneToOneField("apps.orders.Order", on_delete=models.CASCADE)
    name = models.CharField(max_length=100, default='My VPS')
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)
    plan = models.ForeignKey(Plan,  on_delete=models.CASCADE)
    duration = models.ForeignKey(Duration,  on_delete=models.CASCADE)
    operating_system = models.ForeignKey(
        'infrastructure.OperatingSystem',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    ip_address = models.GenericIPAddressField(null = True, blank=True)
    status = models.CharField(max_length=50, choices=StatusChoices.choices, default='inactive')

    history = HistoricalRecords()

    class Meta:
        constraints = [
            UniqueConstraint(
                Lower('name'),
                'user',
                name='unique_vps_name_per_user',
            )
        ]

    def __str__(self):
        return f"VPS {self.name} for User {self.user}"
