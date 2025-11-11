from django.urls import path
from . import views

urlpatterns = [
    path('', views.get_cart, name='get_cart'),
    path('add/', views.add_to_cart, name='add_to_cart'),
    path('update/', views.update_item, name='update_item'),
    path('remove/', views.remove_item, name='remove_item'),
    path('clear/', views.clear_cart, name='clear_cart'),
    path('prepare-checkout/', views.prepare_checkout, name='prepare_checkout'),
]
