"""Règle de répartition validée : 25 % charges, 60 % du reste à Africa Commodities, solde en 3 parts égales."""
from datetime import date
from decimal import Decimal

from django.db import migrations


def creer(apps, schema_editor):
    apps.get_model("repartition", "RegleRepartition").objects.get_or_create(
        date_debut=date(2026, 1, 1),
        defaults=dict(pct_charges=Decimal("25"), pct_africa_commodities=Decimal("60"),
                      parts_risques=1, parts_provision=1, parts_comptes=1,
                      note="Règle initiale validée par la direction (octobre 2026)."),
    )


def supprimer(apps, schema_editor):
    apps.get_model("repartition", "RegleRepartition").objects.filter(date_debut=date(2026, 1, 1)).delete()


class Migration(migrations.Migration):
    dependencies = [("repartition", "0001_initial")]
    operations = [migrations.RunPython(creer, supprimer)]
