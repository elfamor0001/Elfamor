from rest_framework import serializers
from .models import ContactMessage


class ContactMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = ['id', 'name', 'email', 'phone', 'comment', 'created_at', 'is_read', 'is_replied']
        read_only_fields = ['id', 'created_at', 'is_read', 'is_replied']


class ContactFormSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=True, min_length=2)
    email = serializers.EmailField(required=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    comment = serializers.CharField(required=True, min_length=10)

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Name cannot be empty or whitespace.")
        return value.strip()

    def validate_comment(self, value):
        if not value.strip():
            raise serializers.ValidationError("Comment cannot be empty or whitespace.")
        return value.strip()
