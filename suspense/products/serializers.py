from rest_framework import serializers
from .models import Product, FragranceNote, ProductImage


class FragranceNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = FragranceNote
        fields = ['id', 'name', 'description', 'note_type']


class ProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'image_url', 'is_primary', 'created_at', 'product']
        read_only_fields = ['id', 'created_at']

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            return request.build_absolute_uri(obj.image.url) if request else obj.image.url
        return None


class ProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    primary_image = serializers.SerializerMethodField()
    top_notes = FragranceNoteSerializer(many=True, read_only=True)
    heart_notes = FragranceNoteSerializer(many=True, read_only=True)
    base_notes = FragranceNoteSerializer(many=True, read_only=True)
    
    # Stock-related fields
    is_in_stock = serializers.BooleanField(read_only=True)
    stock_status = serializers.CharField(read_only=True)
    
    # IDs for adding/updating notes
    top_note_ids = serializers.PrimaryKeyRelatedField(
        source='top_notes',
        queryset=FragranceNote.objects.filter(note_type='top'),
        many=True,
        write_only=True,
        required=False
    )
    heart_note_ids = serializers.PrimaryKeyRelatedField(
        source='heart_notes',
        queryset=FragranceNote.objects.filter(note_type='heart'),
        many=True,
        write_only=True,
        required=False
    )
    base_note_ids = serializers.PrimaryKeyRelatedField(
        source='base_notes',
        queryset=FragranceNote.objects.filter(note_type='base'),
        many=True,
        write_only=True,
        required=False
    )

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'price', 'description', 'stock',
            'is_in_stock', 'stock_status',
            'top_notes', 'heart_notes', 'base_notes',
            'top_note_ids', 'heart_note_ids', 'base_note_ids',
            'volume_ml', 'images', 'primary_image', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'is_in_stock', 'stock_status']

    def get_primary_image(self, obj):
        primary_image = obj.primary_image
        if primary_image:
            request = self.context.get('request')
            return request.build_absolute_uri(primary_image.url) if request else primary_image.url
        return None