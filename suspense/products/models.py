from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from cloudinary.models import CloudinaryField
from cloudinary import uploader
import logging

logger = logging.getLogger(__name__)


class FragranceNote(models.Model):
    """Model for individual fragrance notes that can be used in perfumes."""
    NOTE_TYPES = [
        ('top', 'Top Note'),
        ('heart', 'Heart Note'),
        ('base', 'Base Note'),
    ]
    
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    note_type = models.CharField(max_length=5, choices=NOTE_TYPES)
    
    class Meta:
        ordering = ['name']
        unique_together = ['name', 'note_type']
    
    def __str__(self):
        return f"{self.name} ({self.get_note_type_display()})"


class Product(models.Model):
    """Perfume product model."""
    name = models.CharField(max_length=150)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)
    top_notes = models.ManyToManyField(
        FragranceNote, 
        related_name='products_as_top',
        limit_choices_to={'note_type': 'top'},
        blank=True
    )
    heart_notes = models.ManyToManyField(
        FragranceNote,
        related_name='products_as_heart',
        limit_choices_to={'note_type': 'heart'},
        blank=True
    )
    base_notes = models.ManyToManyField(
        FragranceNote,
        related_name='products_as_base',
        limit_choices_to={'note_type': 'base'},
        blank=True
    )
    volume_ml = models.PositiveIntegerField(help_text="Volume in milliliters (ml)")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def primary_image(self):
        """Get the primary image for the product."""
        primary = self.images.filter(is_primary=True).first()
        if primary:
            return primary.image
        # Fallback to first image if no primary is set
        first_image = self.images.first()
        return first_image.image if first_image else None


class ProductImage(models.Model):
    """Model for product images."""
    product = models.ForeignKey(Product, related_name='images', on_delete=models.CASCADE)
    image = CloudinaryField(
        'image',
        folder='product_images',
        transformation=[{'quality': 'auto:best'}]
    )
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', '-created_at']

    def save(self, *args, **kwargs):
        """Override save to handle primary image logic."""
        # If this is the first image for the product, make it primary
        if not self.pk and not self.product.images.exists():
            self.is_primary = True
        
        # If this image is being set as primary, update others
        if self.is_primary:
            # Exclude current instance if it exists
            other_images = self.product.images.exclude(pk=self.pk) if self.pk else self.product.images.all()
            other_images.update(is_primary=False)
        
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Delete Cloudinary image when deleting the product image."""
        # If deleting primary image, set another image as primary
        if self.is_primary and self.product.images.exclude(pk=self.pk).exists():
            next_image = self.product.images.exclude(pk=self.pk).first()
            next_image.is_primary = True
            next_image.save()
        
        # Delete the image from Cloudinary
        if self.image:
            try:
                uploader.destroy(self.image.public_id)
            except Exception as e:
                logger.exception("Error deleting Cloudinary file for product image %s: %s", self.pk, e)
        super().delete(*args, **kwargs)

    def __str__(self):
        return f"Image for {self.product.name} ({'Primary' if self.is_primary else 'Secondary'})"