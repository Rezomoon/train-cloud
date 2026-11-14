from django.contrib import admin
from django.urls import path
from apps.users.api.views import RegisterUserView ,LoginView, RefreshTokenView, UserListView, UserProfileView
urlpatterns = [

    path('token/', LoginView.as_view(), name='login'),
    path('token/refresh/', RefreshTokenView.as_view(), name='token-refresh'),
    path('register/', RegisterUserView.as_view(), name='register'),
    path("users/", UserListView.as_view(), name="user-list"),
    path("profile/", UserProfileView.as_view(), name="user-profile"),
]