from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Utilisateur


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Coordonnées", {"fields": ("telephone",)}),)
    list_display = ("username", "email", "first_name", "last_name", "is_staff", "is_active")
