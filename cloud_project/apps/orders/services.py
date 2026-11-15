from django.contrib.auth import get_user_model
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
from apps.vps.models import Duration, Plan, VPS

User = get_user_model()

# Order statuses that still reserve the requested VPS name.
ACTIVE_ORDER_STATUSES = [
    OrderStatusChoices.PENDING_PAYMENT,
    OrderStatusChoices.PAID,
    OrderStatusChoices.PROVISIONING,
]


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

    resolved_vps_name = vps_name or "My VPS"
    total_amount = plan.price * duration.duration_in_month

    with transaction.atomic():
        # Serialize concurrent purchase requests from the same user so two
        # identical names cannot both pass the uniqueness checks below.
        User.objects.select_for_update().get(pk=user.pk)

        name_taken = (
            VPS.objects.filter(
                user=user,
                name__iexact=resolved_vps_name,
            ).exists()
            or Order.objects.filter(
                user=user,
                vps_name__iexact=resolved_vps_name,
                status__in=ACTIVE_ORDER_STATUSES,
            ).exists()
        )
        if name_taken:
            raise ValidationError(
                {
                    "vps_name": (
                        "You already have a VPS or active order with this name."
                    )
                }
            )

        order = Order.objects.create(
            user=user,
            plan=plan,
            duration=duration,
            operating_system=operating_system,
            vps_name=resolved_vps_name,
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
