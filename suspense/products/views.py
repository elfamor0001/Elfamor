from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Product
from .serializers import ProductSerializer


# Create your views here.

# views.py
class ProductListView(APIView):
    def get(self, request):
        products = Product.objects.all()

        # Filter by size
        size = request.GET.get('size')
        if size and size != "All":
            products = products.filter(size=size)

        # Filter by availability (stock)
        availability = request.GET.get('availability')
        if availability == "InStock":
            products = products.filter(stock__gt=0)
        elif availability == "OutOfStock":
            products = products.filter(stock=0)

        # Filter by category (if you have a category field)
        category = request.GET.get('category')
        if category and category != "View All":
            products = products.filter(category=category)

        # Search filter
        search = request.GET.get('search')
        if search:
            from django.db.models import Q
            products = products.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )

        # Sorting
        sort = request.GET.get('sort')
        if sort == "PriceLowHigh":
            products = products.order_by('price')
        elif sort == "PriceHighLow":
            products = products.order_by('-price')
        elif sort == "Newest":
            products = products.order_by('-created_at')
        # else: Featured or default, no sorting or your custom logic

        serializer = ProductSerializer(
            products, 
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)
