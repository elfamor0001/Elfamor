from rest_framework import generics, permissions
from rest_framework.parsers import MultiPartParser, FormParser
from django.db import models
from .models import Product, FragranceNote, ProductImage
from .serializers import ProductSerializer, FragranceNoteSerializer, ProductImageSerializer


class FragranceNoteListCreateView(generics.ListCreateAPIView):
    """API endpoint for listing and creating fragrance notes."""
    queryset = FragranceNote.objects.all().order_by('note_type', 'name')
    serializer_class = FragranceNoteSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        queryset = super().get_queryset()
        note_type = self.request.query_params.get('type', None)
        if note_type:
            queryset = queryset.filter(note_type=note_type)
        return queryset


class FragranceNoteDetailView(generics.RetrieveUpdateDestroyAPIView):
    """API endpoint for retrieving, updating and deleting fragrance notes."""
    queryset = FragranceNote.objects.all()
    serializer_class = FragranceNoteSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class ProductListCreateView(generics.ListCreateAPIView):
    """API endpoint for listing and creating perfume products."""
    queryset = Product.objects.all().order_by('-created_at')
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        queryset = super().get_queryset()
        # Filter by note
        note_id = self.request.query_params.get('note_id', None)
        if note_id:
            queryset = queryset.filter(
                models.Q(top_notes__id=note_id) |
                models.Q(heart_notes__id=note_id) |
                models.Q(base_notes__id=note_id)
            ).distinct()
        return queryset


class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    """API endpoint for retrieving, updating and deleting perfume products."""
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    parser_classes = [MultiPartParser, FormParser]


class ProductImageListCreateView(generics.ListCreateAPIView):
    """API endpoint for listing and creating product images."""
    queryset = ProductImage.objects.all().order_by('-is_primary', '-created_at')
    serializer_class = ProductImageSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        queryset = super().get_queryset()
        product_id = self.request.query_params.get('product_id', None)
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        return queryset


class ProductImageDetailView(generics.RetrieveUpdateDestroyAPIView):
    """API endpoint for retrieving, updating and deleting product images."""
    queryset = ProductImage.objects.all()
    serializer_class = ProductImageSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    parser_classes = [MultiPartParser, FormParser]