from django.db import migrations, models


def populate_hardware_snapshots(apps, schema_editor):
    """Backfill existing VPS rows from their current plan.

    Historical rows are best-effort: they are populated from the plan that is
    still referenced by the historical record, falling back to 0 when the plan
    has since been deleted.
    """
    VPS = apps.get_model("vps", "VPS")
    HistoricalVPS = apps.get_model("vps", "HistoricalVPS")
    Plan = apps.get_model("vps", "Plan")

    plans = {plan.pk: plan for plan in Plan.objects.all()}

    for vps in VPS.objects.all().iterator():
        plan = plans.get(vps.plan_id)
        if plan is None:
            continue
        vps.cpu = plan.cpu
        vps.ram = plan.ram
        vps.storage = plan.storage
        vps.save(update_fields=["cpu", "ram", "storage"])

    for historical in HistoricalVPS.objects.all().iterator():
        plan = plans.get(historical.plan_id)
        if plan is None:
            continue
        historical.cpu = plan.cpu
        historical.ram = plan.ram
        historical.storage = plan.storage
        historical.save(update_fields=["cpu", "ram", "storage"])


def clear_hardware_snapshots(apps, schema_editor):
    """Reverse is a no-op: the fields are removed by the reverse schema ops."""


class Migration(migrations.Migration):

    dependencies = [
        ("vps", "0004_historicalvps_operating_system_vps_operating_system_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="vps",
            name="cpu",
            field=models.IntegerField(default=0),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="vps",
            name="ram",
            field=models.IntegerField(default=0),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="vps",
            name="storage",
            field=models.IntegerField(default=0),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="historicalvps",
            name="cpu",
            field=models.IntegerField(default=0),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="historicalvps",
            name="ram",
            field=models.IntegerField(default=0),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="historicalvps",
            name="storage",
            field=models.IntegerField(default=0),
            preserve_default=False,
        ),
        migrations.RunPython(
            populate_hardware_snapshots,
            clear_hardware_snapshots,
        ),
    ]
