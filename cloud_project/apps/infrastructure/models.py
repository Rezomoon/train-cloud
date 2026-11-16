import uuid

from django.db import models

# Create your models here.

class AuditModel(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        
class Region(AuditModel):
    name = models.CharField(max_length=100)
    description = models.TextField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class OperatingSystem(AuditModel):
    name = models.CharField(max_length=100)
    version = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)
    # Optional mapping to the infrastructure provider's image identifier.
    provider_image_id = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return f"{self.name} {self.version}"

class DataCenter(AuditModel):
    name = models.CharField(max_length=100)
    region = models.ForeignKey(Region, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name
