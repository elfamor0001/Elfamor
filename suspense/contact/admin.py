from django.contrib import admin
from .models import ContactMessage


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'phone', 'created_at', 'is_read', 'is_replied']
    list_filter = ['created_at', 'is_read', 'is_replied']
    search_fields = ['name', 'email', 'phone', 'comment']
    readonly_fields = ['created_at']
    fieldsets = (
        ('Contact Information', {
            'fields': ('name', 'email', 'phone')
        }),
        ('Message', {
            'fields': ('comment',)
        }),
        ('Status', {
            'fields': ('is_read', 'is_replied')
        }),
        ('Timestamps', {
            'fields': ('created_at',)
        }),
    )

    def has_delete_permission(self, request, obj=None):
        # Prevent accidental deletion of contact messages
        return request.user.is_superuser
