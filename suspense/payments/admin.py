from django.contrib import admin
from django.utils.html import format_html
from .models import Order, OrderItem, Payment

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
        'status_badge', 
        'created_at', 
        'payment_status'
    ]
    list_filter = ['status', 'created_at', 'currency']
    search_fields = ['razorpay_order_id', 'user__email', 'user__username']
    readonly_fields = ['razorpay_order_id', 'amount', 'currency', 'created_at', 'updated_at']
    inlines = [OrderItemInline, PaymentInline]
    date_hierarchy = 'created_at'
    list_per_page = 20
    
    fieldsets = (
        ('Order Information', {
            'fields': ('user', 'razorpay_order_id', 'amount', 'currency', 'status')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
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
    status_badge.short_description = 'Status'
    
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