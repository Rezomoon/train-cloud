import pytest
from .factories import OrderFactories
from rest_framework.test import APIClient

#

@pytest.fixture
def api_client():
    return APIClient


@pytest.fixture
def order():
    return OrderFactories()

