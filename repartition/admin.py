from django.contrib import admin

from .models import RegleRepartition


@admin.register(RegleRepartition)
class RegleRepartitionAdmin(admin.ModelAdmin):
    list_display = ("date_debut", "pct_charges", "pct_africa_commodities", "parts_risques",
                    "parts_provision", "parts_comptes", "note")
    readonly_fields = ("cree_le", "modifie_le")

    def get_readonly_fields(self, request, obj=None):
        # Une règle déjà utilisée par des lignes ne se modifie plus : on en crée une nouvelle.
        if obj and obj.lignes.exists():
            return [f.name for f in obj._meta.fields if f.name != "note"]
        return self.readonly_fields

    def has_delete_permission(self, request, obj=None):
        return obj is None or not obj.lignes.exists()
