from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from core.views import accueil, page_introuvable

urlpatterns = [
    path("", accueil, name="accueil"),
    # Connexion, 2FA, mot de passe (allauth). L'admin redirige ici pour se connecter.
    path("compte/signup/", page_introuvable),  # pas d'inscription publique (404 plutôt qu'une page)
    path("compte/", include("allauth.urls")),
    path(settings.ADMIN_URL, admin.site.urls),
]
