import factory
from apps.infrastructure.models import OperatingSystem
#

class OperatingSystemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OperatingSystem
    name = factory.Sequence(lambda n: f"DataCeter_name_{n}")
    version = factory.Sequence(lambda n: f"Version_num_{n}")
    is_active = True
    provider_image_id = factory.Sequence(lambda n: f"Provider_image_id_{n}")