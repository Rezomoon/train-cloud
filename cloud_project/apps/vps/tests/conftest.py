import pytest

from .factories import (
    DurationFactory,
    PlanFactory,
    VPSFactory,
)

from rest_framework.test import APIClient

#


@pytest.fixture
def api_client():
    return APIClient()



@pytest.fixture
def duration():
    return DurationFactory()



@pytest.fixture
def plan():
    return PlanFactory()



@pytest.fixture
def vps():
    return VPSFactory()

