from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from simple_history.admin import SimpleHistoryAdmin

from .models import Affectation, JournalSecurite, Utilisateur


class AffectationInline(admin.TabularInline):
    model = Affectation
    extra = 0
    fields = ("societe", "role", "actif")


class AffectationSocieteInline(AffectationInline):
    fields = ("utilisateur", "role", "actif")
    autocomplete_fields = ("utilisateur",)


@admin.register(Utilisateur)
class UtilisateurAdmin(SimpleHistoryAdmin, UserAdmin):
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


@admin.register(Affectation)
class AffectationAdmin(SimpleHistoryAdmin):
    list_display = ("utilisateur", "societe", "role", "actif", "modifie_le")
    list_filter = ("societe", "role", "actif")
    search_fields = ("utilisateur__email", "utilisateur__last_name", "utilisateur__first_name")
    autocomplete_fields = ("utilisateur",)
    list_select_related = ("utilisateur", "societe")


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
