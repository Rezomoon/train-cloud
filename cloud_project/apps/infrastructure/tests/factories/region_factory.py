from apps.infrastructure.models import Region
import factory

# 

class RegionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Region
    name = factory.Sequence(lambda n : "Region_name_{n}")
    description = factory.Sequence(lambda n : "Descrip_{n}")
    is_active = True