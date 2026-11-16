"""OpenStack adapter built on top of ``openstacksdk``.

The SDK is imported lazily so the project keeps working with the mock provider
even when ``openstacksdk`` is not installed.  All connection details come from
Django settings, therefore switching providers only requires changing
``INFRASTRUCTURE_PROVIDER=openstack`` in the environment.
"""

from django.conf import settings
from openstack import connect
from apps.infrastructure.providers.base import BaseCloudProvider


class OpenStackCloudProvider(BaseCloudProvider):
    """Structural OpenStack implementation of the provider interface."""

    def __init__(self):
        # Imported here so the module can be imported without the SDK installed.
        

        self.connection = connect(
            auth_url=settings.OPENSTACK_AUTH_URL,
            username=settings.OPENSTACK_USERNAME,
            password=settings.OPENSTACK_PASSWORD,
            project_name=settings.OPENSTACK_PROJECT_NAME,
            user_domain_name=settings.OPENSTACK_USER_DOMAIN_NAME,
            project_domain_name=settings.OPENSTACK_PROJECT_DOMAIN_NAME,
            region_name=settings.OPENSTACK_REGION_NAME,
            interface=settings.OPENSTACK_INTERFACE,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _resolve_flavor(self, cpu: int, ram: int, storage: int):
        compute = self.connection.compute

        configured_id = getattr(settings, "OPENSTACK_FLAVOR_ID", None)
        if configured_id:
            return compute.find_flavor(configured_id, ignore_missing=False)

        # Best-effort match on the requested hardware, then fall back to the
        # smallest available flavor so provisioning never fails on naming.
        for flavor in compute.flavors():
            if (
                flavor.vcpus == cpu
                and flavor.ram == ram * 1024
                and flavor.disk == storage
            ):
                return flavor

        return next(iter(compute.flavors()), None)

    def _resolve_image(self, os_name: str):
        image = self.connection.image

        configured_id = getattr(settings, "OPENSTACK_IMAGE_ID", None)
        if configured_id:
            return image.find_image(configured_id, ignore_missing=False)

        return image.find_image(os_name, ignore_missing=True)

    @staticmethod
    def _extract_ip(server) -> str:
        addresses = server.addresses or {}
        for entries in addresses.values():
            for entry in entries:
                if entry.get("addr"):
                    return entry["addr"]
        return ""

    # ------------------------------------------------------------------
    # Provider interface
    # ------------------------------------------------------------------
    def create_instance(
        self,
        name: str,
        cpu: int,
        ram: int,
        storage: int,
        os_name: str,
        region: str,
    ) -> dict:
        compute = self.connection.compute

        flavor = self._resolve_flavor(cpu, ram, storage)
        image = self._resolve_image(os_name)

        networks = []
        network_id = getattr(settings, "OPENSTACK_NETWORK_ID", None)
        if network_id:
            networks.append({"uuid": network_id})

        server = compute.create_server(
            name=name,
            flavor_id=flavor.id,
            image_id=image.id if image else None,
            networks=networks or None,
        )

        server = compute.wait_for_server(
            server,
            wait=getattr(settings, "OPENSTACK_TIMEOUT", 600),
        )

        return {
            "instance_id": server.id,
            "ip_address": self._extract_ip(server),
            "status": server.status,
        }

    def delete_instance(self, instance_id: str) -> bool:
        self.connection.compute.delete_server(instance_id, ignore_missing=True)
        return True

    def get_instance_status(self, instance_id: str) -> dict:
        server = self.connection.compute.get_server(instance_id)
        return {
            "instance_id": instance_id,
            "status": server.status,
        }
