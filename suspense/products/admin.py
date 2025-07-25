from django.contrib import admin
from .models import Product
import cloudinary.uploader

class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'stock', 'size', 'color', 'created_at')
    search_fields = ('name', 'description')
    list_filter = ('size', 'color')

    def delete_queryset(self, request, queryset):
        """Handle bulk deletions in admin"""
        for product in queryset:
            if product.image:
                try:
                    cloudinary.uploader.destroy(product.image.public_id)
                except Exception as e:
                    # Log error but continue deletion
                    self.message_user(request, f"Error deleting image for {product.name}: {e}", level='ERROR')
        super().delete_queryset(request, queryset)

admin.site.register(Product, ProductAdmin)
