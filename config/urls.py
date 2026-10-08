from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core.views import page_introuvable

urlpatterns = [
    # Connexion, 2FA, mot de passe (allauth). L'admin redirige ici pour se connecter.
    path("compte/signup/", page_introuvable),  # pas d'inscription publique (404 plutôt qu'une page)
    path("compte/", include("allauth.urls")),
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include("interface.urls")),
]

if settings.DEBUG:  # en production, Nginx sert les fichiers téléversés
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler403 = "interface.views.erreur_403"
handler404 = "interface.views.erreur_404"
handler500 = "interface.views.erreur_500"
