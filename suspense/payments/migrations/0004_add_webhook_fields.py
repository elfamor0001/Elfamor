# Generated migration for adding webhook-related fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0002_order_shipping_info'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='awb_number',
            field=models.CharField(blank=True, db_index=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='courier_name',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='delivered_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='tracking_data',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
