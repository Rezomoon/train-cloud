from typing import Optional

from django.db import IntegrityError, transaction

from apps.orders.models import Order, OrderStatusChoices
from apps.vps.models import StatusChoices, VPS


def create_vps_from_order(order: Order) -> Optional[VPS]:
    """Create the VPS record for a paid order.

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
                    # TODO: Replace mock IP/status with Infrastructure Provider
                    ip_address="10.10.0.15",
                    status=StatusChoices.Active,
                )
        except IntegrityError:
            order.status = OrderStatusChoices.FAILED
            order.save(update_fields=["status", "updated_at"])
            return None

        order.vps = vps
        order.status = OrderStatusChoices.ACTIVE
        order.save(update_fields=["vps", "status", "updated_at"])

        return vps
