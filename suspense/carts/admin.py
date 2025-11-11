from django.contrib import admin
from .models import Cart, CartItem


class CartItemInline(admin.TabularInline):
	model = CartItem
	extra = 0
	readonly_fields = ('subtotal',)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
	list_display = ('id', 'user', 'created_at', 'updated_at', 'total')
	search_fields = ('user__email', 'user__username')
	inlines = (CartItemInline,)


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
	list_display = ('id', 'cart', 'product', 'quantity', 'subtotal', 'added_at')
	search_fields = ('product__name', 'cart__user__email')
	readonly_fields = ('subtotal',)
