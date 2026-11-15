import decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('infrastructure', '0001_initial'),
        ('vps', '0003_remove_historicalvps_final_price_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('orders', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='order',
            name='resource_price',
        ),
        migrations.RemoveField(
            model_name='order',
            name='amount',
        ),
        migrations.AlterField(
            model_name='order',
            name='user',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='orders',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='order',
            name='plan',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to='vps.plan',
            ),
        ),
        migrations.AlterField(
            model_name='order',
            name='duration',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to='vps.duration',
            ),
        ),
        migrations.AlterField(
            model_name='order',
            name='vps',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='order',
                to='vps.vps',
            ),
        ),
        migrations.AlterField(
            model_name='order',
            name='payment_method',
            field=models.CharField(
                choices=[('wallet', 'Wallet'), ('bank', 'Bank')],
                default='bank',
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending_payment', 'Pending Payment'),
                    ('paid', 'Paid'),
                    ('cancelled', 'Cancelled'),
                    ('failed', 'Failed'),
                ],
                default='pending_payment',
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='operating_system',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='infrastructure.operatingsystem',
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='vps_name',
            field=models.CharField(default='My VPS', max_length=100),
        ),
        migrations.AddField(
            model_name='order',
            name='cpu_snapshot',
            field=models.IntegerField(default=0),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='order',
            name='ram_snapshot',
            field=models.IntegerField(default=0),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='order',
            name='storage_snapshot',
            field=models.IntegerField(default=0),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='order',
            name='unit_price',
            field=models.DecimalField(
                decimal_places=2,
                default=decimal.Decimal('0.00'),
                max_digits=10,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='order',
            name='total_amount',
            field=models.DecimalField(
                decimal_places=2,
                default=decimal.Decimal('0.00'),
                max_digits=10,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='order',
            name='payment_status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('completed', 'Completed'),
                    ('failed', 'Failed'),
                ],
                default='pending',
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='paid_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
