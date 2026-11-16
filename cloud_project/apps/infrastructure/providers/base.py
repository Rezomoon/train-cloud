"""Infrastructure provider abstraction.

Every cloud backend (mock, OpenStack, ...) implements :class:`BaseCloudProvider`
so the service and task layers never depend on a concrete provider.  This keeps
all infrastructure-specific code inside ``apps/infrastructure`` and makes the
backend switchable through the ``INFRASTRUCTURE_PROVIDER`` setting.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ProvisionedInstance:
    """Lightweight, provider-neutral representation of a created instance."""

    instance_id: str
    ip_address: str
    status: str


class BaseCloudProvider(ABC):
    """Common interface for every infrastructure provider."""

    @abstractmethod
    def create_instance(
        self,
        name: str,
        cpu: int,
        ram: int,
        storage: int,
        os_name: str,
        region: str,
    ) -> dict:
        """Create a server and return ``instance_id``, ``ip_address`` and ``status``."""

    @abstractmethod
    def delete_instance(self, instance_id: str) -> bool:
        """Delete a server. Returns ``True`` when the deletion was accepted."""

    @abstractmethod
    def get_instance_status(self, instance_id: str) -> dict:
        """Return the current provider status for a server."""
