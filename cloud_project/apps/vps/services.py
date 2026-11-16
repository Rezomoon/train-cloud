from typing import Optional

from django.db import IntegrityError, transaction

from apps.orders.models import Order, OrderStatusChoices
from apps.vps.models import StatusChoices, VPS


def create_provisioning_vps_from_order(order: Order) -> Optional[VPS]:
    """Create the initial VPS record for a paid order.

    The record starts in ``provisioning`` status with no IP and no provider
    instance id; the Celery provisioning task fills those in asynchronously.
    The function is idempotent: if the order already has a VPS, it is returned
    without creating a second record.
    """
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)

        if order.vps_id:
            return order.vps

        try:
            # Savepoint so a duplicate-name IntegrityError does not break the
            # outer transaction and we can still mark the order as failed.
            with transaction.atomic():
                vps = VPS.objects.create(
                    user=order.user,
                    plan=order.plan,
                    duration=order.duration,
                    operating_system=order.operating_system,
                    name=order.vps_name,
                    cpu=order.cpu_snapshot,
                    ram=order.ram_snapshot,
                    storage=order.storage_snapshot,
                    ip_address=None,
                    provider_instance_id=None,
                    status=StatusChoices.PROVISIONING,
                )
        except IntegrityError:
            order.status = OrderStatusChoices.FAILED
            order.save(update_fields=["status", "updated_at"])
            return None

        order.vps = vps
        order.save(update_fields=["vps", "updated_at"])

        return vps


# Backwards-compatible alias for callers that still use the old name.
create_vps_from_order = create_provisioning_vps_from_order
