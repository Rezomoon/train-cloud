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
    # Optional mapping to the infrastructure provider's flavor identifier.
    provider_flavor_id = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return self.name

class Duration(AuditModel):
    name = models.CharField(max_length=100)
    duration_in_month = models.IntegerField()
    data_center = models.ForeignKey('infrastructure.DataCenter', on_delete=models.CASCADE)

    def __str__(self):
        return self.name

class StatusChoices(models.TextChoices):
    PROVISIONING = "provisioning", "Provisioning"
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    ERROR = "error", "Error"
    TERMINATING = "terminating", "Terminating"
    TERMINATED = "terminated", "Terminated"

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
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    provider_instance_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
    )
    status = models.CharField(
        max_length=50,
        choices=StatusChoices.choices,
        default=StatusChoices.PROVISIONING,
    )

    # Hardware snapshot captured at purchase time so later Plan changes do not
    # affect already provisioned VPS instances.
    cpu = models.IntegerField()
    ram = models.IntegerField()
    storage = models.IntegerField()

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
