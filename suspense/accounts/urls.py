# accounts/urls.py
from django.urls import path
from .views import RegisterView, LoginView, LogoutView, get_csrf_token, session_view

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('csrf/', get_csrf_token, name='get-csrf-token'),
    path('session_view/', session_view, name='session_view')
]
