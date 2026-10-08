from django.contrib.admin import AdminSite
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse

from comptes import acces


class SiteAdministration(AdminSite):
    """Site d'administration réservé à l'admin groupe (et aux superutilisateurs)."""

    site_header = "Groupe – Suivi des marges"
    site_title = "Suivi des marges"
    index_title = "Administration"

    def has_permission(self, request):
        return acces.peut_administrer(request.user)

    def login(self, request, extra_context=None):
        """
        Pas de formulaire de connexion propre à l'admin : tout passe par la connexion allauth
        (donc par la 2FA et par axes). Un utilisateur connecté sans droit reçoit une 403.
        """
        suite = request.GET.get("next") or reverse("admin:index", current_app=self.name)
        if not request.user.is_authenticated:
            return redirect_to_login(suite)
        if self.has_permission(request):
            return redirect(suite)
        acces.signaler_refus(request.user, "admin", chemin=request.path)
        raise PermissionDenied("Accès réservé à l'administrateur du groupe.")
