from django.contrib import admin
from .models import Product, FragranceNote, ProductImage
from cloudinary import uploader
import logging

logger = logging.getLogger(__name__)

@admin.register(FragranceNote)
class FragranceNoteAdmin(admin.ModelAdmin):
    list_display = ('name', 'note_type', 'description')
    list_filter = ('note_type',)
    search_fields = ('name', 'description')


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    readonly_fields = ['created_at']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'volume_ml', 'created_at', 'primary_image_preview')
    search_fields = ('name', 'description')
    filter_horizontal = ('top_notes', 'heart_notes', 'base_notes')
    list_filter = ('created_at',)
    inlines = [ProductImageInline]

    def primary_image_preview(self, obj):
        primary_image = obj.primary_image
        if primary_image:
            return f"✓ Has primary image"
        return "No image"
    primary_image_preview.short_description = 'Primary Image'

    def delete_queryset(self, request, queryset):
        """Handle bulk deletions in admin: remove Cloudinary images first."""
        for product in queryset:
            # Delete all associated images from Cloudinary
            for product_image in product.images.all():
                if product_image.image:
                    try:
                        uploader.destroy(product_image.image.public_id)
                    except Exception as e:
                        logger.exception("Error deleting image for product %s: %s", product.pk, e)
        super().delete_queryset(request, queryset)


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'image_preview', 'is_primary', 'created_at')
    list_filter = ('is_primary', 'created_at')
    search_fields = ('product__name',)
    list_editable = ('is_primary',)
    readonly_fields = ('created_at', 'image_preview')

    def image_preview(self, obj):
        if obj.image:
            return f'<img src="{obj.image.url}" style="max-height: 50px;" />'
        return "No image"
    image_preview.allow_tags = True
    image_preview.short_description = 'Preview'