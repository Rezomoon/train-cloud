from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.infrastructure.models import OperatingSystem
from apps.orders.models import (
    Order,
    OrderStatusChoices,
    PaymentMethodChoices,
    PaymentStatusChoices,
)
from apps.orders.tasks import process_mock_payment_task
from apps.vps.models import Duration, Plan


def create_purchase_order(
    user,
    plan_uuid,
    duration_uuid,
    operating_system_uuid=None,
    vps_name=None,
    payment_method=PaymentMethodChoices.BANK,
):
    """Create a VPS purchase order and enqueue the mock payment task.

    All pricing is calculated server-side; client-provided amounts are ignored.
    """
    plan = Plan.objects.filter(uuid=plan_uuid, is_active=True).first()
    if plan is None:
        raise ValidationError({"plan_uuid": "Active plan not found."})

    duration = Duration.objects.filter(uuid=duration_uuid).first()
    if duration is None:
        raise ValidationError({"duration_uuid": "Duration not found."})

    if plan.data_center_id != duration.data_center_id:
        raise ValidationError(
            {
                "duration_uuid": (
                    "Duration does not belong to the same data center as the plan."
                )
            }
        )

    operating_system = None
    if operating_system_uuid:
        operating_system = OperatingSystem.objects.filter(
            uuid=operating_system_uuid,
            is_active=True,
        ).first()
        if operating_system is None:
            raise ValidationError(
                {"operating_system_uuid": "Active operating system not found."}
            )

    total_amount = plan.price * duration.duration_in_month

    with transaction.atomic():
        order = Order.objects.create(
            user=user,
            plan=plan,
            duration=duration,
            operating_system=operating_system,
            vps_name=vps_name or "My VPS",
            cpu_snapshot=plan.cpu,
            ram_snapshot=plan.ram,
            storage_snapshot=plan.storage,
            unit_price=plan.price,
            total_amount=total_amount,
            payment_method=payment_method,
            payment_status=PaymentStatusChoices.PENDING,
            status=OrderStatusChoices.PENDING_PAYMENT,
        )

        # Only enqueue after the transaction is committed so the worker can
        # always find the order row.
        transaction.on_commit(
            lambda: process_mock_payment_task.delay(str(order.uuid))
        )

    return order
