"""Deterministic, network-free provider used for local development and tests."""

import random
import uuid

from apps.infrastructure.providers.base import BaseCloudProvider


class MockCloudProvider(BaseCloudProvider):
    """Simulates OpenStack without performing any external network call."""

    def create_instance(
        self,
        name: str,
        cpu: int,
        ram: int,
        storage: int,
        os_name: str,
        region: str,
    ) -> dict:
        instance_id = f"mock-inst-{uuid.uuid4().hex[:12]}"
        ip_address = (
            f"10.20.{random.randint(1, 254)}.{random.randint(2, 254)}"
        )
        return {
            "instance_id": instance_id,
            "ip_address": ip_address,
            "status": "ACTIVE",
        }

    def delete_instance(self, instance_id: str) -> bool:
        return True

    def get_instance_status(self, instance_id: str) -> dict:
        return {
            "instance_id": instance_id,
            "status": "ACTIVE",
        }
