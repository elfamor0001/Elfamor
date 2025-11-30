from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Q
from .models import Order, OrderItem, Payment
from .shiprocket_service import ShiprocketService, create_shiprocket_order_from_django_order
import logging
from django.utils.safestring import mark_safe

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
        'subtotal_display',
        'shipment_charge_display',
        'total_amount_display',
        'free_shipping',
        'status_badge', 
        'shipping_status_badge',
        'shipping_partner',
        'created_at', 
        'payment_status'
    ]
    
    list_filter = [
        'status', 
        'shipping_status', 
        'free_shipping',
        'shipping_partner',
        'created_at', 
        'currency'
    ]
    
    search_fields = [
        'razorpay_order_id', 
        'user__email', 
        'user__username', 
        'awb_number',
        'courier_name',
        'shipping_partner'
    ]
    
    readonly_fields = [
        'razorpay_order_id', 'amount', 'currency', 'created_at', 'updated_at', 
        'shiprocket_order_id', 'shipping_partner', 
        'subtotal', 'shipment_charge', 'total_amount', 
        'free_shipping', 'awb_number', 'courier_name', 'delivered_at', 
        'tracking_data_display', 'shipping_info_display'
    ]
    
    fieldsets = (
        ('Order Information', {
            'fields': (
                'user',
                'razorpay_order_id',
                'amount',
                'currency',
                'status',
                'shipping_info_display'
            )
        }),
        ('Shipping Calculation', {
            'fields': (
                'subtotal',
                'shipment_charge',
                'free_shipping',
                'total_amount',
            ),
            'classes': ('collapse',)
        }),
        ('Shiprocket Shipping Details', {
            'fields': (
                'shiprocket_order_id',
                'shipping_status',
                'shipping_partner',
            )
        }),
        ('Advanced Shipping Information', {
            'fields': (
                'awb_number',
                'courier_name',
                'delivered_at',
                'tracking_data_display',
            ),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    # Add the display methods for the new fields
    def subtotal_display(self, obj):
        return f"₹{obj.subtotal}"
    subtotal_display.short_description = 'Subtotal'

    def shipment_charge_display(self, obj):
        return f"₹{obj.shipment_charge}"
    shipment_charge_display.short_description = 'Shipping Charge'

    def total_amount_display(self, obj):
        return f"₹{obj.total_amount}"
    total_amount_display.short_description = 'Total Amount'

    def shipping_info_display(self, obj):
        """Display shipping info in a formatted way"""
        if not obj.shipping_info:
            return "No shipping information provided"
        
        shipping_info = obj.shipping_info
        html = "<div style='padding: 10px; background-color: #f8f9fa; border-radius: 5px; color:black'>"
        
        fields = [
            ('Full Name', shipping_info.get('full_name')),
            ('Email', shipping_info.get('email')),
            ('Phone', shipping_info.get('phone')),
            ('Address Line 1', shipping_info.get('address_line1')),
            ('Address Line 2', shipping_info.get('address_line2')),
            ('City', shipping_info.get('city')),
            ('State', shipping_info.get('state')),
            ('Postal Code', shipping_info.get('postal_code')),
            ('Country', shipping_info.get('country')),
        ]
        
        for label, value in fields:
            if value:
                html += f"<p><strong>{label}:</strong> {value}</p>"
        
        html += "</div>"
        return mark_safe(html)

    shipping_info_display.short_description = 'Shipping Information'

    def tracking_data_display(self, obj):
        """Display tracking data in a formatted way"""
        if not obj.tracking_data:
            return "No tracking data available"
        
        tracking_data = obj.tracking_data
        html = "<div style='padding: 10px; background-color: #f8f9fa; color:black; border-radius: 5px; max-height: 300px; overflow-y: auto;'>"
        
        if isinstance(tracking_data, dict):
            for key, value in tracking_data.items():
                if key.lower() != 'tracking_events':
                    html += f"<p><strong>{key.replace('_', ' ').title()}:</strong> {value}</p>"
            
            tracking_events = tracking_data.get('tracking_events') or tracking_data.get('events') or tracking_data.get('history', [])
            if tracking_events and isinstance(tracking_events, list):
                html += "<h4 style='margin-top: 15px; margin-bottom: 10px;'>Tracking History:</h4>"
                html += "<div style='border-left: 2px solid #007bff; padding-left: 15px;'>"
                
                for event in tracking_events[-10:]:
                    if isinstance(event, dict):
                        date = event.get('date', event.get('timestamp', 'Unknown date'))
                        status = event.get('status', event.get('description', 'Unknown status'))
                        location = event.get('location', event.get('city', ''))
                        
                        html += f"""
                        <div style='margin-bottom: 10px; padding: 8px; background: white; border-radius: 4px;'>
                            <strong>{status}</strong><br>
                            <small>Date: {date}</small>
                            {f"<br><small>Location: {location}</small>" if location else ""}
                        </div>
                        """
                
                html += "</div>"
        
        html += "</div>"
        return mark_safe(html)

    tracking_data_display.short_description = 'Tracking Data'

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
        # Get the status value safely
        status = getattr(obj, 'status', 'created')
        color = status_colors.get(status, 'blue')  # Default to blue if status not found
        
        # Safely get the display value
        try:
            status_display = obj.get_status_display().upper()
        except (AttributeError, ValueError):
            status_display = status.upper()
            
        return format_html(
            '<span style="background-color: {}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 12px;">{}</span>',
            color, status_display
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
        # Get the shipping_status value safely
        shipping_status = getattr(obj, 'shipping_status', 'pending')
        color = status_colors.get(shipping_status, 'lightgray')  # Default to lightgray if status not found
        
        # Safely get the display value
        try:
            status_display = obj.get_shipping_status_display().upper() if shipping_status else 'N/A'
        except (AttributeError, ValueError):
            status_display = shipping_status.upper() if shipping_status else 'N/A'
            
        return format_html(
            '<span style="background-color: {}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 12px;">{}</span>',
            color, status_display
        )
    shipping_status_badge.short_description = 'Shipping Status'
    shipping_status_badge.admin_order_field = 'shipping_status'
    
    def payment_status(self, obj):
        try:
            if hasattr(obj, 'payment') and obj.payment:
                status_colors = {
                    'created': 'blue',
                    'authorized': 'orange',
                    'captured': 'green',
                    'refunded': 'purple',
                    'failed': 'red',
                }
                payment_status = getattr(obj.payment, 'status', 'created')
                color = status_colors.get(payment_status, 'blue')
                
                try:
                    status_display = obj.payment.get_status_display().upper()
                except (AttributeError, ValueError):
                    status_display = payment_status.upper()
                    
                return format_html(
                    '<span style="background-color: {}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 12px;">{}</span>',
                    color, status_display
                )
            return format_html('<span style="color: gray;">No Payment</span>')
        except Exception as e:
            return format_html('<span style="color: gray;">Error: {}</span>', str(e))
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
                        order.shipping_partner = shipment.get('courier_name')
                        
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
            shiprocket_order_id__isnull=False
        )
        
        generated_count = 0
        error_count = 0
        
        service = ShiprocketService()
        
        for order in orders_with_shiprocket:
            try:
                success, label_url = service.generate_label(order.shiprocket_order_id)
                
                if success:
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
        return getattr(obj.order, 'razorpay_order_id', 'N/A')
    order_id.short_description = 'Order ID'
    order_id.admin_order_field = 'order__razorpay_order_id'
    
    def product_name(self, obj):
        return getattr(obj.product, 'name', 'N/A')
    product_name.short_description = 'Product'
    product_name.admin_order_field = 'product__name'
    
    def price_display(self, obj):
        price = getattr(obj, 'price', 0) or 0
        return f"₹{price}"
    price_display.short_description = 'Price'
    
    def item_total_display(self, obj):
        price = getattr(obj, 'price', 0) or 0
        quantity = getattr(obj, 'quantity', 0) or 0
        return f"₹{quantity * price}"
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
admin.site.site_header = "Elfamor Administration"
admin.site.site_title = "Elfamor Admin"
admin.site.index_title = "Welcome to Elfamor Admin Portal"