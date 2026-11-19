import factory
from apps.vps.models import VPS , StatusChoices
from .duration_factory import DurationFactory
from .plan_factory import PlanFactory
from apps.users.tests.factories import UserFactory
from apps.infrastructure.tests.factories import OperatingSystemFactory
#

class VPSFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VPS
    name = factory.Sequence( lambda n : f"vps-name-{n:02d}")
    user = factory.SubFactory(UserFactory)
    plan = factory.SubFactory(PlanFactory)
    duration = factory.SubFactory(DurationFactory)
    operating_system = factory.SubFactory(OperatingSystemFactory)
    ip_address =  factory.Faker("ipv6")
    provider_instance_id = factory.Sequence(lambda n : f"prov-ins-int-{n:02d}")
    status = StatusChoices.ACTIVE
    cpu = 16
    ram = 16
    storage = 16
