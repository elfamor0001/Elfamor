from django.db import models
from django.conf import settings
from products.models import Product


class Cart(models.Model):
	"""A shopping cart tied to a user."""
	user = models.OneToOneField(
		settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cart'
	)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return f"Cart ({self.user})"

	@property
	def total(self):
		"""Return total price for the cart as Decimal."""
		total = sum(item.subtotal for item in self.items.all())
		return total


class CartItem(models.Model):
	cart = models.ForeignKey(Cart, related_name='items', on_delete=models.CASCADE)
	product = models.ForeignKey(Product, on_delete=models.CASCADE)
	quantity = models.PositiveIntegerField(default=1)
	added_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		unique_together = ('cart', 'product')

	def __str__(self):
		return f"{self.quantity} x {self.product.name}"

	@property
	def subtotal(self):
		return self.product.price * self.quantity
