"""Provider factory.

Services and Celery tasks call :func:`get_infrastructure_provider` and remain
completely unaware of which backend is configured.
"""

from django.conf import settings

from apps.infrastructure.providers.base import (
    BaseCloudProvider,
    ProvisionedInstance,
)
from apps.infrastructure.providers.mock import MockCloudProvider

__all__ = [
    "BaseCloudProvider",
    "ProvisionedInstance",
    "MockCloudProvider",
    "get_infrastructure_provider",
]


def get_infrastructure_provider() -> BaseCloudProvider:
    """Return the provider selected by the ``INFRASTRUCTURE_PROVIDER`` setting."""

    provider_name = getattr(
        settings, "INFRASTRUCTURE_PROVIDER", "mock"
    ).strip().lower()

    if provider_name == "mock":
        return MockCloudProvider()

    if provider_name == "openstack":
        # Imported lazily so the OpenStack SDK is optional.
        from apps.infrastructure.providers.openstack import (
            OpenStackCloudProvider,
        )

        return OpenStackCloudProvider()

    raise ValueError(
        f"Unsupported INFRASTRUCTURE_PROVIDER: '{provider_name}'. "
        "Expected 'mock' or 'openstack'."
    )
