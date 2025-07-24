from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

class CustomUserAdmin(UserAdmin):
    # Fix list_display to match our model
    list_display = ('email', 'username', 'is_staff', 'date_joined')
    readonly_fields = ('date_joined', 'last_login')

    # Fix fieldsets for add/change views
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('username', 'phone', 'avatar')}),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'password1', 'password2'),
        }),
    )
    
    # Restrict fields for non-superusers
    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if not request.user.is_superuser:
            fieldsets = (
                (None, {'fields': ('username', 'email', 'phone', 'avatar')}),
                ('Permissions', {'fields': ('is_active',)}),
            )
        return fieldsets

admin.site.register(CustomUser, CustomUserAdmin)