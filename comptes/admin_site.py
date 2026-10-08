from django.contrib.admin import AdminSite

from comptes import acces


class SiteAdministration(AdminSite):
    """Site d'administration réservé à l'admin groupe (et aux superutilisateurs)."""

    site_header = "Groupe – Suivi des marges"
    site_title = "Suivi des marges"
    index_title = "Administration"

    def has_permission(self, request):
        return acces.peut_administrer(request.user)
