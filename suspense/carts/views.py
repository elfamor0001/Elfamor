from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .models import Cart, CartItem
from .serializers import CartSerializer, CartItemSerializer
from products.models import Product


def _get_or_create_cart(user):
	cart, _ = Cart.objects.get_or_create(user=user)
	return cart


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_cart(request):
	cart = _get_or_create_cart(request.user)
	serializer = CartSerializer(cart, context={'request': request})
	data = serializer.data
	# include calculated total
	data['total'] = cart.total
	return Response(data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_to_cart(request):
	"""Add a product to the user's cart. Payload: {product_id, quantity} """
	product_id = request.data.get('product_id')
	quantity = int(request.data.get('quantity', 1))

	if not product_id:
		return Response({'error': 'product_id required'}, status=status.HTTP_400_BAD_REQUEST)

	product = get_object_or_404(Product, id=product_id)
	cart = _get_or_create_cart(request.user)

	item, created = CartItem.objects.get_or_create(cart=cart, product=product)
	if not created:
		item.quantity = item.quantity + quantity
	else:
		item.quantity = quantity
	item.save()

	serializer = CartItemSerializer(item, context={'request': request})
	return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_item(request):
	"""Update the quantity of a cart item. Payload: {product_id, quantity} """
	product_id = request.data.get('product_id')
	quantity = int(request.data.get('quantity', 0))

	if not product_id:
		return Response({'error': 'product_id required'}, status=status.HTTP_400_BAD_REQUEST)

	cart = _get_or_create_cart(request.user)
	try:
		item = CartItem.objects.get(cart=cart, product_id=product_id)
	except CartItem.DoesNotExist:
		return Response({'error': 'Item not in cart'}, status=status.HTTP_404_NOT_FOUND)

	if quantity <= 0:
		item.delete()
		return Response({'detail': 'Item removed'})

	item.quantity = quantity
	item.save()
	serializer = CartItemSerializer(item, context={'request': request})
	return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def remove_item(request):
	product_id = request.data.get('product_id')
	if not product_id:
		return Response({'error': 'product_id required'}, status=status.HTTP_400_BAD_REQUEST)

	cart = _get_or_create_cart(request.user)
	try:
		item = CartItem.objects.get(cart=cart, product_id=product_id)
		item.delete()
	except CartItem.DoesNotExist:
		return Response({'error': 'Item not in cart'}, status=status.HTTP_404_NOT_FOUND)

	return Response({'detail': 'Item removed'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def clear_cart(request):
	cart = _get_or_create_cart(request.user)
	cart.items.all().delete()
	return Response({'detail': 'Cart cleared'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def prepare_checkout(request):
	"""Return items payload suitable for payments.create_order.

	Response format:
	{
	  "items": [{"product_id": 1, "quantity": 2}, ...],
	  "total": "123.45"
	}
	"""
	cart = _get_or_create_cart(request.user)
	items = []
	for item in cart.items.select_related('product').all():
		items.append({'product_id': item.product.id, 'quantity': item.quantity})

	return Response({'items': items, 'total': cart.total})
