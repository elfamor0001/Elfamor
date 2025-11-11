from django.urls import path
from . import views

urlpatterns = [
    path('create-order/', views.create_order, name='create-order'),
    path('verify-payment/', views.verify_payment, name='verify-payment'),
     path('check-payment-status/', views.check_payment_status, name='check-payment-status'),
    path('webhook/', views.razorpay_webhook, name='razorpay-webhook'),
    path('orders/', views.order_history, name='order-history'),
    path('orders/<int:order_id>/', views.order_detail, name='order-detail'),
    path('orders/<int:order_id>/cancel/', views.cancel_order, name='cancel-order'),
]