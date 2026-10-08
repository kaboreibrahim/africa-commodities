"""Outils communs aux tests de l'interface."""
import re
from contextlib import contextmanager

from django.db import connection
from django.test.utils import CaptureQueriesContext

from comptes.tests.jeu import JeuUtilisateursMixin, activer_totp

# Requêtes de session et d'authentification, exclues du décompte (cf. cahier des charges),
# ainsi que le COUNT(*) de la pagination.
REQUETES_EXCLUES = re.compile(
    r'"django_session"|"comptes_utilisateur"|"mfa_authenticator"|"__count"|SAVEPOINT', re.IGNORECASE
)

HTMX = {"HTTP_HX_REQUEST": "true"}


class JeuInterfaceMixin(JeuUtilisateursMixin):
    """Jeu d'utilisateurs de l'étape 2 ; 2FA activée pour les rôles qui l'exigent."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        for user in (cls.admin_groupe, cls.responsable_ooa):
            activer_totp(user)

    def connecter(self, user):
        self.client.force_login(user)


@contextmanager
def compter_requetes():
    """Capture les requêtes SQL utiles (hors session, authentification et pagination)."""
    with CaptureQueriesContext(connection) as contexte:
        resultat = {}
        yield resultat
    resultat["requetes"] = [q["sql"] for q in contexte.captured_queries if not REQUETES_EXCLUES.search(q["sql"])]
    resultat["nombre"] = len(resultat["requetes"])
