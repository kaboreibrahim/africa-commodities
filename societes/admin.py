from django.contrib import admin

from comptes.admin import AffectationSocieteInline

from .models import Client, ObjectifMensuel, Societe


class ObjectifInline(admin.TabularInline):
    model = ObjectifMensuel
    extra = 1
    fields = ("mois", "montant")


@admin.register(Societe)
class SocieteAdmin(admin.ModelAdmin):
    list_display = ("code", "nom", "libelle_ligne", "unite", "marge_defaut", "objectif_defaut", "actif", "ordre")
    list_editable = ("ordre", "actif")
    search_fields = ("code", "nom")
    inlines = [ObjectifInline, AffectationSocieteInline]
    fieldsets = (
        (None, {"fields": ("code", "nom", "actif", "ordre", "logo")}),
        ("Libellés de l'activité", {"fields": ("libelle_ligne", "libelle_ligne_pluriel", "libelle_reference",
                                               "libelle_quantite", "libelle_marge", "unite")}),
        ("Champ spécifique", {"fields": ("champ_extra_libelle", "champ_extra_type", "champ_extra_choix")}),
        ("Valeurs par défaut", {"fields": ("marge_defaut", "objectif_defaut")}),
        ("Charte graphique", {"fields": ("couleur_principale", "couleur_foncee", "couleur_accent", "couleur_serie"),
                              "classes": ("collapse",)}),
    )


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("nom", "societe", "telephone", "email")
    list_filter = ("societe",)
    search_fields = ("nom", "email", "telephone")
    list_select_related = ("societe",)


@admin.register(ObjectifMensuel)
class ObjectifMensuelAdmin(admin.ModelAdmin):
    list_display = ("societe", "mois", "montant")
    list_filter = ("societe",)
    date_hierarchy = "mois"
