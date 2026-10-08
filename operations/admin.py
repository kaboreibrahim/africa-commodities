from django.contrib import admin, messages
from django.contrib.humanize.templatetags.humanize import intcomma
from simple_history.admin import SimpleHistoryAdmin

from . import services
from .models import Ligne


def fcfa(v):
    return f"{intcomma(int(v))} F" if v is not None else "—"


@admin.register(Ligne)
class LigneAdmin(SimpleHistoryAdmin):
    list_display = ("date", "societe", "reference", "projet", "client", "quantite", "marge_unitaire_f",
                    "marge_totale_f", "africa_commodities_f", "comptes_f")
    list_filter = ("societe", ("date", admin.DateFieldListFilter), "regle")
    search_fields = ("reference", "projet", "client__nom", "observation", "extra")
    date_hierarchy = "date"
    autocomplete_fields = ("client",)
    list_select_related = ("societe", "client")
    list_per_page = 50
    readonly_fields = ("regle", "marge_totale", "part_charges", "part_africa_commodities", "part_risques",
                       "part_provision", "part_comptes", "cree_par", "cree_le", "modifie_par", "modifie_le")
    fieldsets = (
        (None, {"fields": ("societe", "date", "extra", "reference", "projet", "client",
                           "quantite", "marge_unitaire", "observation")}),
        ("Répartition (calculée automatiquement)", {"fields": readonly_fields[:7]}),
        ("Traçabilité", {"fields": ("cree_par", "cree_le", "modifie_par", "modifie_le"), "classes": ("collapse",)}),
    )
    actions = ["suppression_douce"]

    @admin.display(description="Marge unit.", ordering="marge_unitaire")
    def marge_unitaire_f(self, o): return fcfa(o.marge_unitaire)

    @admin.display(description="Marge totale", ordering="marge_totale")
    def marge_totale_f(self, o): return fcfa(o.marge_totale)

    @admin.display(description="Africa Com.", ordering="part_africa_commodities")
    def africa_commodities_f(self, o): return fcfa(o.part_africa_commodities)

    @admin.display(description="Comptes", ordering="part_comptes")
    def comptes_f(self, o): return fcfa(o.part_comptes)

    def get_readonly_fields(self, request, obj=None):
        # Une ligne ne change pas de société : on la supprime et on la recrée.
        return self.readonly_fields + (("societe",) if obj else ())

    def save_model(self, request, obj, form, change):
        # Les écritures passent par les services (droits, validation, traçabilité).
        if change:
            donnees = {champ: form.cleaned_data[champ] for champ in form.changed_data}
            services.modifier_ligne(request.user, Ligne.tous.get(pk=obj.pk), **donnees)
        else:
            donnees = {champ: valeur for champ, valeur in form.cleaned_data.items() if champ != "societe"}
            obj.pk = services.creer_ligne(request.user, obj.societe, **donnees).pk
        obj.refresh_from_db()

    # Suppression douce à la place de la suppression définitive
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    @admin.action(description="Supprimer (restaurable) les lignes sélectionnées")
    def suppression_douce(self, request, queryset):
        n = 0
        for ligne in queryset:
            services.supprimer_ligne(request.user, ligne)
            n += 1
        self.message_user(request, f"{n} ligne(s) supprimée(s). Elles restent restaurables.", messages.SUCCESS)
