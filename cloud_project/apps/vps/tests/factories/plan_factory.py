import factory
from apps.vps.models import Plan
import decimal
from apps.infrastructure.tests.factories import DataCenterSystemFactory
#

class PlanFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Plan

    name = factory.Sequence(lambda n: f"Plan_{n:02d}")

    price = factory.Faker(
        "pydecimal",
        left_digits = 5,
        right_digits = 2,
        positive = True
    )
    description = factory.Sequence(lambda st : f"Desc {st}")
    cpu = 16
    ram = 16
    storage = 16
    is_active = True
    data_center = factory.SubFactory(DataCenterSystemFactory) # TODO
    provider_flavor_id = factory.Sequence(lambda n: f"pro_{n:02d}")
