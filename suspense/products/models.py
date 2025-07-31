from django.db import models
from datetime import datetime
from cloudinary.models import CloudinaryField
import uuid
import logging

logger = logging.getLogger(__name__)


# Create your models here.
class Product(models.Model):
    SIZE_CHOICES = [
        ('XS', 'XS'), ('S', 'S'), ('M', 'M'),
        ('L', 'L'), ('XL', 'XL'), ('XXL', 'XXL'),
    ]
    COLOR_CHOICES = [
        ('white', 'White'), ('black', 'Black'), ('red', 'Red'),
        ('blue', 'Blue'), ('green', 'Green'),
    ]
    CATEGORY_CHOICES = [
        ('T-Shirts', 'T-Shirts'),
        ('Polos', 'Polos'),
        ('Shirts', 'Shirts'),
        ('Jackets', 'Jackets'),
        ('Hoodies', 'Hoodies'),
        ('Sweatshirts', 'Sweatshirts'),
        ('Cargos', 'Cargos'),
        ('Jeans', 'Jeans'),
        ('Shorts', 'Shorts'),
        ('Pants', 'Pants'),
    ]

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = CloudinaryField(
        'image', 
        folder='product_images', 
        blank=True, 
        null=True,
        transformation=[{'quality': 'auto:best'}]
    )
    stock = models.PositiveIntegerField(default=0)
    size = models.CharField(max_length=5, choices=SIZE_CHOICES)
    color = models.CharField(max_length=20, choices=COLOR_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='T-Shirts')
    
    def delete(self, *args, **kwargs):
        """Override delete method to remove image from Cloudinary"""
        if self.image:
            try:
                # Delete image from Cloudinary before deleting model
                uploader.destroy(self.image.public_id)
            except Exception as e:
                # Handle errors but don't block deletion
                print(f"Error deleting Cloudinary file: {e}")
        super().delete(*args, **kwargs)

    def __str__(self):
        return self.name