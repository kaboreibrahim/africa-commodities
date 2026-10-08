from django.contrib import admin, messages

from comptes.admin import AffectationSocieteInline

from . import services
from .models import Client, ObjectifMensuel, Societe


class ObjectifInline(admin.TabularInline):
    """Lecture seule : les objectifs se gèrent dans « Objectifs mensuels » (via les services)."""

    model = ObjectifMensuel
    extra = 0
    fields = ("mois", "montant")
    readonly_fields = fields
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


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
    actions = ["suppression_douce"]

    def get_readonly_fields(self, request, obj=None):
        return ("societe",) if obj else ()

    def save_model(self, request, obj, form, change):
        donnees = {champ: form.cleaned_data[champ] for champ in services.CHAMPS_CLIENT if champ in form.cleaned_data}
        if change:
            services.modifier_client(request.user, Client.tous.get(pk=obj.pk), **donnees)
        else:
            obj.pk = services.ajouter_client(request.user, obj.societe, **donnees).pk
        obj.refresh_from_db()

    # Suppression douce à la place de la suppression définitive
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    @admin.action(description="Retirer (restaurable) les clients sélectionnés")
    def suppression_douce(self, request, queryset):
        for client in queryset:
            services.retirer_client(request.user, client)
        self.message_user(request, f"{len(queryset)} client(s) retiré(s).", messages.SUCCESS)


@admin.register(ObjectifMensuel)
class ObjectifMensuelAdmin(admin.ModelAdmin):
    list_display = ("societe", "mois", "montant")
    list_filter = ("societe",)
    date_hierarchy = "mois"

    def save_model(self, request, obj, form, change):
        if change:
            # Changer de société ou de mois revient à remplacer l'ancien objectif.
            ancien = ObjectifMensuel.objects.get(pk=obj.pk)
            if (ancien.societe_id, ancien.mois) != (obj.societe_id, obj.mois.replace(day=1)):
                services.supprimer_objectif(request.user, ancien)
        obj.pk = services.definir_objectif(request.user, obj.societe, obj.mois, obj.montant).pk
        obj.refresh_from_db()

    def delete_model(self, request, obj):
        services.supprimer_objectif(request.user, obj)

    def delete_queryset(self, request, queryset):
        for objectif in queryset:
            services.supprimer_objectif(request.user, objectif)
