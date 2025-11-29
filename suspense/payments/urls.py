from django.urls import path
from . import views
from .webhook_handler import shiprocket_webhook, webhook_health_check

urlpatterns = [
    path('create-order/', views.create_order, name='create-order'),
    path('verify-payment/', views.verify_payment, name='verify-payment'),
    path('check-payment-status/', views.check_payment_status, name='check-payment-status'),
    path('webhook/', views.razorpay_webhook, name='razorpay-webhook'),
    path('orders/', views.order_history, name='order-history'),
    path('orders/<int:order_id>/', views.order_detail, name='order-detail'),
    path('orders/<int:order_id>/cancel/', views.cancel_order, name='cancel-order'),
    
    # Shiprocket Shipping Integration
    path('tracking/<int:order_id>/', views.get_tracking, name='get-tracking'),
    path('calculate-shipping/', views.calculate_shipping_view, name='calculate-shipping'),
    path('create-shipment/<int:order_id>/', views.create_shipment, name='create-shipment'),
    path('cancel-shipment/<int:order_id>/', views.cancel_shipment, name='cancel-shipment'),
    path('generate-label/<int:order_id>/', views.generate_label, name='generate-label'),
    path('shipping-status/<int:order_id>/', views.order_shipping_status, name='shipping-status'),
    
    # Shiprocket Webhook Endpoints
    path('webhooks/shipping-events/', shiprocket_webhook, name='shiprocket-webhook'),
    path('webhooks/shiprocket/health/', webhook_health_check, name='webhook-health-check'),
]