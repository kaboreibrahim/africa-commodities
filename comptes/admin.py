from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Affectation, Utilisateur


class AffectationInline(admin.TabularInline):
    model = Affectation
    extra = 0
    fields = ("societe", "role", "actif")


class AffectationSocieteInline(AffectationInline):
    fields = ("utilisateur", "role", "actif")
    autocomplete_fields = ("utilisateur",)


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
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
