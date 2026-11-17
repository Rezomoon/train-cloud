from typing import Optional

from django.db import IntegrityError, transaction
from rest_framework.exceptions import NotFound, ValidationError

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


TERMINABLE_STATUSES = [
    StatusChoices.ACTIVE,
    StatusChoices.INACTIVE,
    StatusChoices.ERROR,
]


def request_vps_termination(user, vps_uuid) -> VPS:
    """Request termination of a VPS owned by ``user``.

    The VPS is locked for the duration of the state change so two concurrent
    requests cannot both enqueue the termination task. The Celery task is only
    queued after the transaction commits, so a rollback never leaves an
    orphaned task behind.
    """
    with transaction.atomic():
        try:
            vps = VPS.objects.select_for_update().get(uuid=vps_uuid, user=user)
        except VPS.DoesNotExist:
            raise NotFound("VPS not found.")

        if vps.status == StatusChoices.TERMINATED:
            raise ValidationError({"detail": "This VPS is already terminated."})

        if vps.status == StatusChoices.TERMINATING:
            raise ValidationError(
                {"detail": "Termination is already in progress for this VPS."}
            )

        if vps.status == StatusChoices.PROVISIONING:
            raise ValidationError(
                {"detail": "Cannot terminate a VPS while it is still provisioning."}
            )

        if vps.status not in TERMINABLE_STATUSES:
            raise ValidationError(
                {"detail": f"Cannot terminate a VPS with status '{vps.status}'."}
            )

        vps.status = StatusChoices.TERMINATING
        vps.save(update_fields=["status", "updated_at"])

        from apps.vps.tasks import terminate_vps_task

        transaction.on_commit(lambda: terminate_vps_task.delay(str(vps.uuid)))

        return vps
