import factory
from apps.users.models import User

#
# class UserFactory(factory.django.DjangoModelFactory):
    
#     class Meta:
#         model = User

#     mobeil = factory.Sequence(lambda n: f"091200011{n:02d}")
#     role = 'user'
#     password = factory.Sequence(lambda n: f"abc{n}")
#     email = factory.Sequence(lambda n: f"email{n}@example.com")
#     national_id = factory.Sequence(lambda n:f"111{n:03d}")


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        
    mobile = factory.Sequence(lambda n: f"091{n:07d}")
    role = "user"
    national_id = factory.Sequence(lambda n: f"123{n:05d}")
    is_active = True
    is_staff = False
    is_superuser = True
