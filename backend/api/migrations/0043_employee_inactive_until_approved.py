from django.db import migrations, models


def deactivate_unapproved_employees(apps, schema_editor):
    Employee = apps.get_model("api", "Employee")
    Contract = apps.get_model("api", "Contract")
    approved_employee_ids = Contract.objects.filter(
        status="active",
        signature_status="signed",
        worker_approval_status="approved",
    ).values_list("employee_id", flat=True)
    Employee.objects.exclude(pk__in=approved_employee_ids).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [("api", "0042_salary_advance_charge")]

    operations = [
        migrations.AlterField(
            model_name="employee",
            name="is_active",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(deactivate_unapproved_employees, migrations.RunPython.noop),
    ]
