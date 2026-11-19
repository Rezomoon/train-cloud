import pytest
from django.contrib.auth import get_user_model

#




@pytest.fixture()
def user(db):
    User = get_user_model()

    return User.objects.create_user(
        mobile = "09140986592",
        password="123456",
        role= "user"
    )

def test_user_mobile(user):
    print(user)
    assert user.mobile == "09140986592"