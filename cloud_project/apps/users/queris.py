from django.contrib.auth import authenticate, get_user_model

#

user = get_user_model()

def all_users():
    return user.objects.all()
