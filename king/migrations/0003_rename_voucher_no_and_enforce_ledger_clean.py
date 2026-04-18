from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('king', '0002_workorder_gst_number'),
    ]

    operations = [
        migrations.RenameField(
            model_name='ledgerentry',
            old_name='voucher_no',
            new_name='voucher_number',
        ),
    ]
