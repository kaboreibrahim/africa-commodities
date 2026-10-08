from allauth.mfa.models import Authenticator
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

from comptes import acces


class MFAObligatoireMiddleware:
    """
    Après connexion, impose dans l'ordre :
    1. le changement du mot de passe provisoire (`doit_changer_mot_de_passe`) ;
    2. l'activation de la 2FA (TOTP) pour les rôles de `MFA_ROLES_OBLIGATOIRES`.

    Les pages de compte (allauth), la déconnexion et les fichiers statiques restent accessibles.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        redirection = self.redirection(request)
        return redirect(redirection) if redirection else self.get_response(request)

    def redirection(self, request) -> str | None:
        user = request.user
        if not user.is_authenticated or request.path.startswith(f"/{settings.STATIC_URL.lstrip('/')}"):
            return None
        url_mdp = reverse("account_change_password")
        url_deconnexion = reverse("account_logout")
        if user.doit_changer_mot_de_passe:
            return None if request.path in (url_mdp, url_deconnexion) else url_mdp
        if self.mfa_manquante(user):
            prefixe_comptes = reverse("account_login").rsplit("login/", 1)[0]  # « /compte/ »
            return None if request.path.startswith(prefixe_comptes) else reverse("mfa_activate_totp")
        return None

    @staticmethod
    def mfa_manquante(user) -> bool:
        if not acces.roles_de(user) & set(settings.MFA_ROLES_OBLIGATOIRES):
            return False
        return not Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).exists()
