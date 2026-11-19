import factory
from apps.infrastructure.models import DataCenter
from .region_factory import RegionFactory
# 

class DataCenterSystemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DataCenter
    name = factory.Sequence(lambda n: f"Operatin_sys_name_{n}")
    region = factory.SubFactory(RegionFactory)
    is_active = True

