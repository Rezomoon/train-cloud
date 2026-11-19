import factory
from apps.vps.models import Duration
from apps.infrastructure.tests.factories import DataCenterSystemFactory
#
class DurationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Duration
    name = factory.Sequence(lambda n: f"Duration_name_{n}")
    duration_in_month = factory.Sequence(lambda n: n + 1)
    data_center = factory.SubFactory(DataCenterSystemFactory)