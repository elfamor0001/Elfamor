# accounts/urls.py
from django.urls import path
from .views import RegisterView, LoginView, LogoutView, get_csrf_token, session_view, verify_email, PhoneLoginView, RequestLoginCodeView, VerifyPhoneView, SendVerificationCodeView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('csrf/', get_csrf_token, name='get-csrf-token'),
    path('session_view/', session_view, name='session_view'),
    path('verify_email/<uidb64>/<token>/', verify_email, name='verify_email'),
    path('phone-login/', PhoneLoginView.as_view(), name='phone_login'),
    path('request-login-code/', RequestLoginCodeView.as_view(), name='request_login_code'),
    path('verify-phone/', VerifyPhoneView.as_view(), name='verify_phone'),
    path('send-verification-code/', SendVerificationCodeView.as_view(), name='send_verification_code'),
]
