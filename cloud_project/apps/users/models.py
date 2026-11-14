from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from simple_history.models import HistoricalRecords
# Create your models here.



class AuditableModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True





class UserRole(models.TextChoices):
    ADMIN = "admin"
    USER = "user"


class UserManager(BaseUserManager):
    def _create_user(self, mobile, password=None, **extra_fields):
        if not mobile:
            raise ValueError("The Mobile field must be set")
        user = self.model(mobile=mobile, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_user(self, mobile, password=None, **extra_fields):
        if not mobile:
            raise ValueError("The Mobile field must be set")
        if extra_fields.get('role') is None:
            extra_fields['role'] = UserRole.USER    
        return self._create_user(mobile, password, **extra_fields)


    def create_superuser(self, mobile, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        if extra_fields.get('role') != UserRole.ADMIN:
            raise ValueError('Superuser must have role=admin.')

        return self.create_user(mobile, password, **extra_fields)




class User(AbstractUser, AuditableModel):
    # Add any additional fields or methods specific to your user model here
    username = None
    email = models.EmailField(unique=True) 
    mobile = models.CharField(max_length=15, unique=True)
    role = models.CharField(max_length=10, choices=UserRole.choices, default=UserRole.USER)
    national_id = models.CharField(max_length=20, unique=True)

    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_superuser = models.BooleanField(default=False)
    history = HistoricalRecords()

    USERNAME_FIELD = "mobile"
    REQUIRED_FIELDS = []

    objects = UserManager()


