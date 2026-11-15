from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.orders.models import (
    Order,
    OrderStatusChoices,
    PaymentStatusChoices,
)


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

        # TODO: Trigger VPS provisioning task here
