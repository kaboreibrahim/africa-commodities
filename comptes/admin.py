from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from simple_history.admin import SimpleHistoryAdmin

from .models import Affectation, HabilitationVueGroupe, JournalSecurite, Utilisateur


class AffectationInline(admin.TabularInline):
    model = Affectation
    fk_name = "utilisateur"
    extra = 0
    fields = ("societe", "role", "actif", "date_debut", "date_fin", "motif")


class AffectationSocieteInline(AffectationInline):
    fk_name = "societe"
    fields = ("utilisateur", "role", "actif", "date_debut", "date_fin", "motif")
    autocomplete_fields = ("utilisateur",)


@admin.register(Utilisateur)
class UtilisateurAdmin(SimpleHistoryAdmin, UserAdmin):
    """
    Les habilitations se gèrent de préférence depuis l'écran « Habilitations » de l'application
    (motif, journal détaillé, effet immédiat). Les modifications faites ici sont tout de même historisées.
    """

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Informations personnelles", {"fields": ("first_name", "last_name", "email", "telephone")}),
        ("Droits", {"fields": ("is_active", "role_global", "is_superuser", "doit_changer_mot_de_passe")}),
        ("Dates importantes", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",),
                "fields": ("username", "email", "first_name", "last_name", "role_global", "password1", "password2")}),
    )
    readonly_fields = ("last_login", "date_joined")
    list_display = ("username", "email", "first_name", "last_name", "role_global", "is_active")
    list_filter = ("role_global", "is_active", "affectations__societe", "affectations__role")
    inlines = [AffectationInline]
    history_list_display = ["role_global", "is_active", "is_superuser"]

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, Affectation):
                instance.accorde_par = request.user
            instance.save()
        for objet in formset.deleted_objects:
            objet.delete()
        formset.save_m2m()


@admin.register(Affectation)
class AffectationAdmin(SimpleHistoryAdmin):
    list_display = ("utilisateur", "societe", "role", "actif", "date_debut", "date_fin", "modifie_le")
    list_filter = ("societe", "role", "actif")
    search_fields = ("utilisateur__email", "utilisateur__last_name", "utilisateur__first_name")
    autocomplete_fields = ("utilisateur",)
    list_select_related = ("utilisateur", "societe")

    def save_model(self, request, obj, form, change):
        obj.accorde_par = request.user
        super().save_model(request, obj, form, change)


@admin.register(HabilitationVueGroupe)
class HabilitationVueGroupeAdmin(SimpleHistoryAdmin):
    """Lecture seule : l'écran « Habilitations » de l'application est le seul moyen de les modifier (motif obligatoire)."""

    list_display = ("utilisateur", "portee", "detail_autorise", "actif", "date_debut", "date_fin", "motif")
    list_filter = ("portee", "detail_autorise", "actif")
    search_fields = ("utilisateur__email", "utilisateur__last_name")
    list_select_related = ("utilisateur",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(JournalSecurite)
class JournalSecuriteAdmin(admin.ModelAdmin):
    """Lecture seule : le journal ne se modifie pas (purge : commande `purger_journal`)."""

    list_display = ("date", "evenement", "utilisateur", "identifiant_saisi", "ip", "details")
    list_filter = ("evenement", ("date", admin.DateFieldListFilter), ("utilisateur", admin.RelatedOnlyFieldListFilter))
    search_fields = ("identifiant_saisi", "utilisateur__email", "ip")
    date_hierarchy = "date"
    list_select_related = ("utilisateur",)
    list_per_page = 100

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
