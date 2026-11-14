from django.contrib import admin
from django.urls import path
from apps.users.api.views import RegisterUserView ,LoginView
urlpatterns = [

    path('login/', LoginView.as_view(), name='login'),
    path('register/', RegisterUserView.as_view(), name='register'),
]