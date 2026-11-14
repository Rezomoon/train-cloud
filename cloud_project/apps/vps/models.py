from django.db import models

# Create your models here.

class Plan(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField()
    cpu = models.IntegerField()
    ram = models.IntegerField()
    storage = models.IntegerField()
    is_active = models.BooleanField(default=True)
    

    def __str__(self):
        return self.name