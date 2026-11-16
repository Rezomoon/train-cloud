from celery import shared_task
from django.db import transaction

from apps.orders.models import (
    Order,
    OrderStatusChoices,
)
from apps.vps.models import StatusChoices, VPS
from apps.vps.services import create_provisioning_vps_from_order


@shared_task
def provision_vps_task(order_uuid: str):
    """Provision the VPS for a paid order through the configured provider.

    The task is idempotent and safe to retry:

    * the order row is locked while reading/updating lifecycle state;
    * if the order is already active, or the VPS already has a provider
      instance id, the task exits without touching the provider;
    * the provider call happens *outside* the database lock so provider
      latency never holds a row lock;
    * failures mark both the VPS and the order accordingly.
    """
    # ------------------------------------------------------------------
    # Phase 1: lock the order, guard against duplicate work, gather input.
    # ------------------------------------------------------------------
    with transaction.atomic():
        try:
            order = (
                Order.objects.select_for_update(of=("self",))
                .select_related(
                    "plan__data_center__region",
                    "operating_system",
                    "vps",
                )
                .get(uuid=order_uuid)
            )
        except Order.DoesNotExist:
            return {"status": "skipped", "reason": "order_not_found"}

        if order.status == OrderStatusChoices.ACTIVE or (
            order.vps_id and order.vps.provider_instance_id
        ):
            return {"status": "skipped", "reason": "already_provisioned"}

        vps = order.vps
        if vps is None:
            vps = create_provisioning_vps_from_order(order)
            if vps is None:
                return {"status": "failed", "reason": "vps_creation_failed"}

        vps_id = vps.pk
        payload = {
            "name": order.vps_name,
            "cpu": order.cpu_snapshot,
            "ram": order.ram_snapshot,
            "storage": order.storage_snapshot,
            "os_name": (
                f"{order.operating_system.name} "
                f"{order.operating_system.version}"
                if order.operating_system_id
                else "ubuntu"
            ),
            "region": order.plan.data_center.region.name,
        }

    # ------------------------------------------------------------------
    # Phase 2: call the provider without holding any database lock.
    # ------------------------------------------------------------------
    try:
        # Imported lazily so the Celery module can load before Django apps.
        from apps.infrastructure.providers import get_infrastructure_provider

        provider = get_infrastructure_provider()
        result = provider.create_instance(**payload)
    except Exception as exc:  # noqa: BLE001 - provider errors are recorded
        with transaction.atomic():
            vps = VPS.objects.select_for_update().get(pk=vps_id)
            vps.status = StatusChoices.ERROR
            vps.save(update_fields=["status", "updated_at"])

            order = Order.objects.select_for_update().get(uuid=order_uuid)
            order.status = OrderStatusChoices.FAILED
            order.save(update_fields=["status", "updated_at"])

        return {"status": "failed", "error": str(exc)}

    # ------------------------------------------------------------------
    # Phase 3: persist the provider result.
    # ------------------------------------------------------------------
    with transaction.atomic():
        vps = VPS.objects.select_for_update().get(pk=vps_id)
        order = Order.objects.select_for_update().get(uuid=order_uuid)

        # Re-check after the network call: another worker may have finished.
        if order.status == OrderStatusChoices.ACTIVE or vps.provider_instance_id:
            return {"status": "skipped", "reason": "already_provisioned"}

        vps.provider_instance_id = result["instance_id"]
        vps.ip_address = result["ip_address"]
        vps.status = StatusChoices.ACTIVE
        vps.save(
            update_fields=[
                "provider_instance_id",
                "ip_address",
                "status",
                "updated_at",
            ]
        )

        order.status = OrderStatusChoices.ACTIVE
        order.save(update_fields=["status", "updated_at"])

    return {
        "status": "active",
        "instance_id": result["instance_id"],
        "ip_address": result["ip_address"],
    }
