from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.infrastructure.models import OperatingSystem
from apps.orders.gateways import charge_mock_payment
from apps.orders.models import (
    Order,
    OrderStatusChoices,
    PaymentMethodChoices,
    PaymentStatusChoices,
)
from apps.vps.models import Duration, Plan, VPS
from apps.vps.services import create_provisioning_vps_from_order

User = get_user_model()

# Order statuses that still reserve the requested VPS name.
ACTIVE_ORDER_STATUSES = [
    OrderStatusChoices.PENDING_PAYMENT,
    OrderStatusChoices.PAID,
    OrderStatusChoices.PROVISIONING,
    OrderStatusChoices.ACTIVE,
]


def create_purchase_order(
    user,
    plan_uuid,
    duration_uuid,
    operating_system_uuid=None,
    vps_name=None,
    payment_method=PaymentMethodChoices.BANK,
):
    """Create a VPS purchase order awaiting an explicit payment request.

    All pricing is calculated server-side; client-provided amounts are ignored.
    This function deliberately does not trigger payment or VPS creation.
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

    return order


def process_order_payment(user, order_uuid, simulate_failure=False):
    """Charge an order through the mock gateway and provision its VPS.

    Returns a tuple of ``(order, gateway_response)``. Gateway failures are
    returned (not raised) so the API can respond with the updated order data.
    """
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(
                uuid=order_uuid,
                user=user,
            )
        except Order.DoesNotExist:
            raise NotFound("Order not found.")

        # Idempotency guard: paying twice is an explicit API error.
        if (
            order.payment_status == PaymentStatusChoices.COMPLETED
            or order.status in (
                OrderStatusChoices.PAID,
                OrderStatusChoices.ACTIVE,
            )
        ):
            raise ValidationError(
                {"detail": "This order has already been paid."}
            )

        if order.status != OrderStatusChoices.PENDING_PAYMENT:
            raise ValidationError(
                {
                    "detail": (
                        f"Cannot pay for an order in '{order.status}' status."
                    )
                }
            )

        gateway_response = charge_mock_payment(
            order.uuid,
            order.total_amount,
            order.payment_method,
            simulate_failure=simulate_failure,
        )

        if gateway_response["success"]:
            order.payment_status = PaymentStatusChoices.COMPLETED
            order.status = OrderStatusChoices.PROVISIONING
            order.paid_at = timezone.now()
            order.payment_reference = gateway_response["reference_id"]
            order.save(
                update_fields=[
                    "payment_status",
                    "status",
                    "paid_at",
                    "payment_reference",
                    "updated_at",
                ]
            )

            # Create the initial VPS row in "provisioning" state. Hardware is
            # taken from the order snapshot, not from the mutable plan.
            vps = create_provisioning_vps_from_order(order)
            order.refresh_from_db() # TODO 

            # Enqueue asynchronous provisioning only once the payment
            # transaction has actually committed.
            if vps is not None:
                from apps.vps.tasks import provision_vps_task

                transaction.on_commit(
                    lambda: provision_vps_task.delay(str(order.uuid))
                )
        else:
            order.payment_status = PaymentStatusChoices.FAILED
            order.status = OrderStatusChoices.FAILED
            order.payment_reference = gateway_response["reference_id"]
            order.save(
                update_fields=[
                    "payment_status",
                    "status",
                    "payment_reference",
                    "updated_at",
                ]
            )

    return order, gateway_response
