from rest_framework import serializers
from .models import Address, CustomUser

class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ['id', 'full_name', 'phone', 'email', 'address_line1', 'city', 'state', 'pincode', 'label', 'custom_label', 'is_default']
        read_only_fields = ['id', 'user']

    def create(self, validated_data):
        user = self.context['request'].user
        # If this is the first address, make it default
        if not Address.objects.filter(user=user).exists():
            validated_data['is_default'] = True
        elif validated_data.get('is_default'):
            # If creating a default address, unmark others
            Address.objects.filter(user=user, is_default=True).update(is_default=False)
        
        return Address.objects.create(user=user, **validated_data)

    def update(self, instance, validated_data):
        if validated_data.get('is_default'):
            Address.objects.filter(user=instance.user, is_default=True).exclude(id=instance.id).update(is_default=False)
        return super().update(instance, validated_data)
