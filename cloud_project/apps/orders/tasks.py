from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.orders.models import (
    Order,
    OrderStatusChoices,
    PaymentStatusChoices,
)
from apps.vps.services import create_vps_from_order


@shared_task
def provision_vps_task(order_uuid: str):
    """Create the VPS record for a paid order (mock provisioning)."""
    order = Order.objects.get(uuid=order_uuid)
    return create_vps_from_order(order)


@shared_task
def process_mock_payment_task(order_uuid: str):
    """Mock payment processor.

    This task intentionally performs no external HTTP calls. It only updates
    the order's payment/lifecycle fields and is safe to run more than once.
    """
    with transaction.atomic():
        order = Order.objects.select_for_update().get(uuid=order_uuid)

        # Idempotency guard: already processed or no longer awaiting payment.
        if (
            order.payment_status == PaymentStatusChoices.COMPLETED
            or order.status != OrderStatusChoices.PENDING_PAYMENT
        ):
            return

        order.payment_status = PaymentStatusChoices.COMPLETED
        order.status = OrderStatusChoices.PAID
        order.paid_at = timezone.now()
        order.save(
            update_fields=[
                "payment_status",
                "status",
                "paid_at",
                "updated_at",
            ]
        )

        # Provisioning is decoupled from payment and only enqueued after the
        # payment transaction commits.
        transaction.on_commit(
            
            lambda: provision_vps_task.delay(str(order.uuid))
        )
