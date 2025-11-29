from django.db import models
from django.conf import settings
from products.models import Product

class Order(models.Model):
    ORDER_STATUS = [
        ('created', 'Created'),
        ('attempted', 'Attempted'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    SHIPPING_STATUS = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('in_transit', 'In Transit'),
        ('out_for_delivery', 'Out for Delivery'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('failed', 'Failed'),
        ('returned', 'Returned'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='orders')
    razorpay_order_id = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default='created')
    shipping_info = models.JSONField(default=dict, blank=True)

    # Shipping charge system fields
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipment_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    free_shipping = models.BooleanField(default=False)

    # Shiprocket shipping fields
    shiprocket_order_id = models.IntegerField(null=True, blank=True, db_index=True)
    shipping_status = models.CharField(max_length=50, choices=SHIPPING_STATUS, default='pending', blank=True)
    tracking_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    shipping_partner = models.CharField(max_length=100, blank=True, null=True)  # e.g., 'Fedex', 'DTDC'
    tracking_url = models.URLField(blank=True, null=True)
    shipping_label_url = models.URLField(blank=True, null=True)

    # Webhook-related fields
    awb_number = models.CharField(max_length=100, blank=True, null=True, db_index=True)  # Airway Bill number
    courier_name = models.CharField(max_length=100, blank=True, null=True)  # Courier partner name
    delivered_at = models.DateTimeField(null=True, blank=True)  # Delivery timestamp
    tracking_data = models.JSONField(default=dict, blank=True)  # Full tracking history

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        FREE_SHIPPING_THRESHOLD = 3000
        SHIPPING_CHARGE = 70
        if self.subtotal >= FREE_SHIPPING_THRESHOLD:
            self.shipment_charge = 0
            self.free_shipping = True
        else:
            self.shipment_charge = SHIPPING_CHARGE
            self.free_shipping = False
        self.total_amount = self.subtotal + self.shipment_charge
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Order {self.razorpay_order_id} - {self.user.email}"
class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    
    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

class Payment(models.Model):
    PAYMENT_STATUS = [
        ('created', 'Created'),
        ('authorized', 'Authorized'),
        ('captured', 'Captured'),
        ('refunded', 'Refunded'),
        ('failed', 'Failed'),
    ]
    
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment')
    razorpay_payment_id = models.CharField(max_length=100, unique=True)
    razorpay_signature = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='created')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    method = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Payment {self.razorpay_payment_id} - {self.status}"