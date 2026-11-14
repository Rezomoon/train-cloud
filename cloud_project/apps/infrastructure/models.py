from django.db import models

# Create your models here.


class Region(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class OperatingSystem(models.Model):
    name = models.CharField(max_length=100)
    version = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} {self.version}"