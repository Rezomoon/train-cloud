import pytest
from .factories import OperatingSystemFactory, RegionFactory, DataCenterSystemFactory
from rest_framework.test import APIClient

#


@pytest.fixture
def api_client():
    return APIClient

@pytest.fixture
def operating_sys():
    return OperatingSystemFactory

@pytest.fixture
def region():
    return RegionFactory

@pytest.fixture
def data_center():
    return DataCenterSystemFactory
