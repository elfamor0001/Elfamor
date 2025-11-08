from django.urls import path
from .views import (
    ProductListCreateView, ProductDetailView,
    FragranceNoteListCreateView, FragranceNoteDetailView,
    ProductImageListCreateView, ProductImageDetailView
)

urlpatterns = [
    # Fragrance Note endpoints
    path('notes/', FragranceNoteListCreateView.as_view(), name='fragrancenote-list'),
    path('notes/<int:pk>/', FragranceNoteDetailView.as_view(), name='fragrancenote-detail'),
    
    # Product endpoints
    path('products/', ProductListCreateView.as_view(), name='product-list'),
    path('products/<int:pk>/', ProductDetailView.as_view(), name='product-detail'),
    
    # Product Image endpoints
    path('product-images/', ProductImageListCreateView.as_view(), name='productimage-list'),
    path('product-images/<int:pk>/', ProductImageDetailView.as_view(), name='productimage-detail'),
]