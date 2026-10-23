from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("api", "0041_activity_monitoring")]

    operations = [
        migrations.AddField(
            model_name="payrollpolicy",
            name="advance_charge_percent",
            field=models.DecimalField(
                decimal_places=2, default=Decimal("18.00"), max_digits=5,
                validators=[django.core.validators.MinValueValidator(Decimal("0")),
                            django.core.validators.MaxValueValidator(Decimal("100"))],
            ),
        ),
        migrations.AddField(model_name="salaryadvance", name="charge_percent",
                            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=5,
                            validators=[django.core.validators.MinValueValidator(Decimal("0")),
                                        django.core.validators.MaxValueValidator(Decimal("100"))])),
        migrations.AddField(model_name="salaryadvance", name="charge_amount",
                            field=models.DecimalField(decimal_places=2, default=0, max_digits=12,
                            validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
        migrations.AddField(model_name="salaryadvance", name="total_repayment",
                            field=models.DecimalField(decimal_places=2, default=0, max_digits=12,
                            validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
        migrations.AddField(model_name="salaryadvancerequest", name="charge_percent",
                            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=5,
                            validators=[django.core.validators.MinValueValidator(Decimal("0")),
                                        django.core.validators.MaxValueValidator(Decimal("100"))])),
        migrations.AddField(model_name="salaryadvancerequest", name="charge_amount",
                            field=models.DecimalField(decimal_places=2, default=0, max_digits=12,
                            validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
        migrations.AddField(model_name="salaryadvancerequest", name="total_repayment",
                            field=models.DecimalField(decimal_places=2, default=0, max_digits=12,
                            validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
    ]
