import factory
from apps.orders.models import Order, PaymentMethodChoices, PaymentStatusChoices, OrderStatusChoices
from apps.users.tests.factories import UserFactory
from apps.vps.tests.factories import PlanFactory, DurationFactory, VPSFactory
from apps.infrastructure.tests.factories import OperatingSystemFactory
#

class OrderFactories(factory.django.DjangoModelFactory):
    class Meta:
        model = Order
    user = factory.SubFactory(UserFactory)
    plan = factory.SubFactory(PlanFactory)
    duration = factory.SubFactory(DurationFactory)
    operating_system = factory.SubFactory(OperatingSystemFactory)
    vps = factory.SubFactory(VPSFactory)
    vps_name =  factory.Sequence(lambda n : f"vps_name_{n:02d}" )
    cpu_snapshot = 16
    ram_snapshot = 16
    storage_snapshot = 16
    unit_price = 100 
    total_amount = 100
    payment_method = PaymentMethodChoices.BANK
    payment_status = PaymentStatusChoices.COMPLETED
    status =  OrderStatusChoices.PENDING_PAYMENT
