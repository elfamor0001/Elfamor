from django.urls import path
from . import views

urlpatterns = [
    path('submit/', views.submit_contact_form, name='submit_contact_form'),
    path('messages/', views.get_contact_messages, name='get_contact_messages'),
    path('messages/<int:message_id>/read/', views.mark_message_as_read, name='mark_message_as_read'),
]
