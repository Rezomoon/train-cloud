import random
import uuid


def create_mock_instance(
    name: str,
    cpu: int,
    ram: int,
    storage: int,
    os_name: str = "",
    region: str = "",
) -> dict:
    """Simulate creating a VPS instance and return mock ID, IP, and status."""
    return {
        "instance_id": f"mock-inst-{uuid.uuid4().hex[:12]}",
        "ip_address": f"10.20.{random.randint(1, 254)}.{random.randint(2, 254)}",
        "status": "ACTIVE",
    }


def delete_mock_instance(instance_id: str) -> bool:
    """Simulate deleting a VPS instance."""
    return True


def get_mock_instance_status(instance_id: str) -> dict:
    """Simulate checking a VPS instance status."""
    return {
        "instance_id": instance_id,
        "status": "ACTIVE",
    }
