from django.contrib import admin
from django.urls import path
from apps.users.api.views import RegisterUserView ,LoginView, UserListView
urlpatterns = [

    path('login/', LoginView.as_view(), name='login'),
    path('register/', RegisterUserView.as_view(), name='register'),
    path("users/", UserListView.as_view(), name="user-list")
]