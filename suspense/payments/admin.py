from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Q
from .models import Order, OrderItem, Payment
from .shiprocket_service import ShiprocketService, create_shiprocket_order_from_django_order
import logging

logger = logging.getLogger(__name__)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    readonly_fields = ['product', 'quantity', 'price', 'item_total']
    extra = 0
    can_delete = False
    
    def item_total(self, obj):
        if obj.price is None or obj.quantity is None:
            return "₹0"
        return f"₹{obj.quantity * obj.price}"
    item_total.short_description = 'Item Total'

class PaymentInline(admin.StackedInline):
    model = Payment
    readonly_fields = ['razorpay_payment_id', 'razorpay_signature', 'amount', 'currency', 'method', 'created_at']
    extra = 0
    can_delete = False
    max_num = 1

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        'razorpay_order_id', 
        'user_email', 
        'amount_display', 
        'subtotal',
        'shipment_charge',
        'total_amount',
        'free_shipping',
        'status_badge', 
        'shipping_status_badge',
        'created_at', 
        'payment_status'
    ]
    list_filter = ['status', 'shipping_status', 'created_at', 'currency']
    search_fields = ['razorpay_order_id', 'user__email', 'user__username', 'tracking_id']
    readonly_fields = ['razorpay_order_id', 'amount', 'currency', 'created_at', 'updated_at', 'shiprocket_order_id', 'tracking_id', 'shipping_partner', 'tracking_url', 'shipping_label_url', 'subtotal', 'shipment_charge', 'total_amount', 'free_shipping']
    inlines = [OrderItemInline, PaymentInline]
    date_hierarchy = 'created_at'
    list_per_page = 20
    
    fieldsets = (
    ('Order Information', {
        'fields': (
            'user',
            'razorpay_order_id',
            'amount',
            'currency',
            'status',
            'shipping_info'
        )
    }),
    ('Shiprocket Shipping Details', {
        'fields': (
            'shiprocket_order_id',
            'shipping_status',
            'tracking_id',
            'shipping_partner',
            'tracking_url',
            'shipping_label_url',
        ),
        'classes': ('wide',)
    }),
    ('Timestamps', {
        'fields': ('created_at', 'updated_at'),
        'classes': ('wide',)
    }),
)

    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User Email'
    user_email.admin_order_field = 'user__email'
    
    def amount_display(self, obj):
        return f"₹{obj.amount}"
    amount_display.short_description = 'Amount'
    amount_display.admin_order_field = 'amount'
    
    def status_badge(self, obj):
        status_colors = {
            'created': 'blue',
            'attempted': 'orange',
            'paid': 'green',
            'failed': 'red',
            'cancelled': 'gray',
        }
        color = status_colors.get(obj.status, 'blue')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 12px;">{}</span>',
            color, obj.get_status_display().upper()
        )
    status_badge.short_description = 'Payment Status'
    
    def shipping_status_badge(self, obj):
        """Display shipping status with color coding"""
        status_colors = {
            'pending': 'lightgray',
            'processing': 'orange',
            'shipped': 'blue',
            'in_transit': 'skyblue',
            'out_for_delivery': 'yellow',
            'delivered': 'green',
            'cancelled': 'red',
            'failed': 'darkred',
            'returned': 'purple',
        }
        color = status_colors.get(obj.shipping_status, 'lightgray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 12px;">{}</span>',
            color, obj.get_shipping_status_display().upper() if obj.shipping_status else 'N/A'
        )
    shipping_status_badge.short_description = 'Shipping Status'
    shipping_status_badge.admin_order_field = 'shipping_status'
    
    def payment_status(self, obj):
        if hasattr(obj, 'payment'):
            status_colors = {
                'created': 'blue',
                'authorized': 'orange',
                'captured': 'green',
                'refunded': 'purple',
                'failed': 'red',
            }
            color = status_colors.get(obj.payment.status, 'blue')
            return format_html(
                '<span style="background-color: {}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 12px;">{}</span>',
                color, obj.payment.get_status_display().upper()
            )
        return format_html('<span style="color: gray;">No Payment</span>')
    payment_status.short_description = 'Payment Status'

    # Custom actions for Shiprocket management
    actions = ['create_shiprocket_order', 'get_tracking_info', 'generate_shipping_label', 'cancel_shiprocket_order']

    def create_shiprocket_order(self, request, queryset):
        """Create Shiprocket orders for selected paid orders"""
        paid_orders = queryset.filter(status='paid', shiprocket_order_id__isnull=True)
        
        created_count = 0
        error_count = 0
        
        for order in paid_orders:
            try:
                success, response = create_shiprocket_order_from_django_order(order)
                
                if success:
                    shiprocket_data = response.get('data', {})
                    order.shiprocket_order_id = shiprocket_data.get('order_id')
                    order.shipping_status = 'processing'
                    order.save()
                    created_count += 1
                    logger.info(f"Shiprocket order created via admin: {order.id}")
                else:
                    error_count += 1
                    logger.error(f"Failed to create Shiprocket order for {order.id}: {response}")
            except Exception as e:
                error_count += 1
                logger.error(f"Error creating Shiprocket order for {order.id}: {str(e)}")
        
        message = f"Successfully created {created_count} Shiprocket orders"
        if error_count > 0:
            message += f" ({error_count} errors)"
        self.message_user(request, message)
    
    create_shiprocket_order.short_description = "Create Shiprocket order for selected paid orders"

    def get_tracking_info(self, request, queryset):
        """Get tracking information for selected orders"""
        orders_with_shiprocket = queryset.filter(shiprocket_order_id__isnull=False)
        
        updated_count = 0
        error_count = 0
        
        service = ShiprocketService()
        
        for order in orders_with_shiprocket:
            try:
                success, tracking_data = service.get_tracking(order.shiprocket_order_id)
                
                if success:
                    shipments = tracking_data.get('shipments', [])
                    if shipments:
                        shipment = shipments[0]
                        order.tracking_id = shipment.get('track_id')
                        order.shipping_partner = shipment.get('courier_name')
                        order.tracking_url = shipment.get('track_url')
                        
                        # Map Shiprocket status to our status choices
                        status_map = {
                            'processing': 'processing',
                            'ready_to_ship': 'processing',
                            'shipped': 'shipped',
                            'in_transit': 'in_transit',
                            'out_for_delivery': 'out_for_delivery',
                            'delivered': 'delivered',
                            'cancelled': 'cancelled',
                            'rto': 'returned',
                        }
                        
                        shiprocket_status = shipment.get('status', '').lower()
                        order.shipping_status = status_map.get(shiprocket_status, order.shipping_status)
                        order.save()
                        updated_count += 1
                        logger.info(f"Tracking updated for order {order.id}")
                else:
                    error_count += 1
            except Exception as e:
                error_count += 1
                logger.error(f"Error getting tracking for order {order.id}: {str(e)}")
        
        message = f"Updated tracking for {updated_count} orders"
        if error_count > 0:
            message += f" ({error_count} errors)"
        self.message_user(request, message)
    
    get_tracking_info.short_description = "Get tracking info from Shiprocket"

    def generate_shipping_label(self, request, queryset):
        """Generate shipping labels for selected orders"""
        orders_with_shiprocket = queryset.filter(
            shiprocket_order_id__isnull=False,
            shipping_label_url__isnull=True
        )
        
        generated_count = 0
        error_count = 0
        
        service = ShiprocketService()
        
        for order in orders_with_shiprocket:
            try:
                success, label_url = service.generate_label(order.shiprocket_order_id)
                
                if success:
                    order.shipping_label_url = label_url
                    order.save()
                    generated_count += 1
                    logger.info(f"Shipping label generated for order {order.id}")
                else:
                    error_count += 1
            except Exception as e:
                error_count += 1
                logger.error(f"Error generating label for order {order.id}: {str(e)}")
        
        message = f"Generated {generated_count} shipping labels"
        if error_count > 0:
            message += f" ({error_count} errors)"
        self.message_user(request, message)
    
    generate_shipping_label.short_description = "Generate shipping labels"

    def cancel_shiprocket_order(self, request, queryset):
        """Cancel Shiprocket orders"""
        orders_to_cancel = queryset.filter(
            shiprocket_order_id__isnull=False,
            shipping_status__in=['pending', 'processing']
        )
        
        cancelled_count = 0
        error_count = 0
        
        service = ShiprocketService()
        
        for order in orders_to_cancel:
            try:
                success, response = service.cancel_order(order.shiprocket_order_id)
                
                if success:
                    order.shipping_status = 'cancelled'
                    order.save()
                    cancelled_count += 1
                    logger.info(f"Shiprocket order cancelled via admin: {order.id}")
                else:
                    error_count += 1
                    logger.error(f"Failed to cancel Shiprocket order {order.id}: {response}")
            except Exception as e:
                error_count += 1
                logger.error(f"Error cancelling Shiprocket order {order.id}: {str(e)}")
        
        message = f"Cancelled {cancelled_count} Shiprocket orders"
        if error_count > 0:
            message += f" ({error_count} errors)"
        self.message_user(request, message)
    
    cancel_shiprocket_order.short_description = "Cancel Shiprocket orders"


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['order_id', 'product_name', 'quantity', 'price_display', 'item_total_display']
    list_filter = ['order__status']
    search_fields = ['order__razorpay_order_id', 'product__name']
    readonly_fields = ['order', 'product', 'quantity', 'price']
    
    def order_id(self, obj):
        return obj.order.razorpay_order_id
    order_id.short_description = 'Order ID'
    order_id.admin_order_field = 'order__razorpay_order_id'
    
    def product_name(self, obj):
        return obj.product.name
    product_name.short_description = 'Product'
    product_name.admin_order_field = 'product__name'
    
    def price_display(self, obj):
        return f"₹{obj.price}"
    price_display.short_description = 'Price'
    
    def item_total_display(self, obj):
        if obj.price is None or obj.quantity is None:
            return "₹0"
        return f"₹{obj.quantity * obj.price}"
    item_total_display.short_description = 'Total'

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        'razorpay_payment_id', 
        'order_id', 
        'amount_display', 
        'status_badge', 
        'method', 
        'created_at'
    ]
    list_filter = ['status', 'method', 'created_at', 'currency']
    search_fields = ['razorpay_payment_id', 'order__razorpay_order_id', 'order__user__email']
    readonly_fields = [
        'order', 
        'razorpay_payment_id', 
        'razorpay_signature', 
        'amount', 
        'currency', 
        'created_at'
    ]
    
    fieldsets = (
        ('Payment Information', {
            'fields': ('order', 'razorpay_payment_id', 'status', 'amount', 'currency', 'method')
        }),
        ('Razorpay Details', {
            'fields': ('razorpay_signature', 'description'),
            'classes': ('collapse',)
        }),
        ('Timestamp', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def order_id(self, obj):
        return obj.order.razorpay_order_id
    order_id.short_description = 'Order ID'
    order_id.admin_order_field = 'order__razorpay_order_id'
    
    def amount_display(self, obj):
        return f"₹{obj.amount}"
    amount_display.short_description = 'Amount'
    amount_display.admin_order_field = 'amount'
    
    def status_badge(self, obj):
        status_colors = {
            'created': 'blue',
            'authorized': 'orange',
            'captured': 'green',
            'refunded': 'purple',
            'failed': 'red',
        }
        color = status_colors.get(obj.status, 'blue')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 12px;">{}</span>',
            color, obj.get_status_display().upper()
        )
    status_badge.short_description = 'Status'

    # Custom actions
    actions = ['mark_as_refunded', 'mark_as_failed']

    def mark_as_refunded(self, request, queryset):
        updated = queryset.update(status='refunded')
        self.message_user(request, f'{updated} payments marked as refunded.')
    mark_as_refunded.short_description = "Mark selected payments as refunded"

    def mark_as_failed(self, request, queryset):
        updated = queryset.update(status='failed')
        self.message_user(request, f'{updated} payments marked as failed.')
    mark_as_failed.short_description = "Mark selected payments as failed"

# Custom admin site header and title
admin.site.site_header = "Perfume Store Administration"
admin.site.site_title = "Perfume Store Admin"
admin.site.index_title = "Welcome to Perfume Store Admin Portal"