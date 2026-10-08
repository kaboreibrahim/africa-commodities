from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from comptes.tests.jeu import JeuUtilisateursMixin, activer_totp
from operations.models import Ligne


class LigneAdminTests(JeuUtilisateursMixin, TestCase):
    """L'admin passe par les services : cree_par / modifie_par remplis, suppression douce."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        activer_totp(cls.admin_groupe)  # 2FA obligatoire pour l'admin groupe

    def setUp(self):
        self.client.force_login(self.admin_groupe)
        self.url = f"/{settings.ADMIN_URL}operations/ligne/"

    def test_ajout_par_l_admin(self):
        reponse = self.client.post(f"{self.url}add/", {
            "societe": self.ooa.pk, "date": timezone.localdate().strftime("%d/%m/%Y"), "reference": "ADMIN-1",
            "quantite": 2, "marge_unitaire": 100_000, "extra": "", "projet": "", "observation": "", "client": "",
        })
        self.assertEqual(reponse.status_code, 302, getattr(reponse, "context", None) and reponse.context.get("errors"))
        ligne = Ligne.objects.get(reference="ADMIN-1")
        self.assertEqual(ligne.cree_par, self.admin_groupe)
        self.assertEqual(ligne.marge_totale, 200_000)

    def test_modification_par_l_admin(self):
        ligne = self.ligne_saisie_ooa
        reponse = self.client.post(f"{self.url}{ligne.pk}/change/", {
            "date": ligne.date.strftime("%d/%m/%Y"), "reference": ligne.reference, "quantite": 5,
            "marge_unitaire": 100_000, "extra": "", "projet": "", "observation": "", "client": "",
        })
        self.assertEqual(reponse.status_code, 302)
        ligne.refresh_from_db()
        self.assertEqual((ligne.marge_totale, ligne.modifie_par, ligne.cree_par),
                         (500_000, self.admin_groupe, self.saisie_ooa))

    def test_suppression_douce_par_l_admin(self):
        self.client.post(self.url, {"action": "suppression_douce", "_selected_action": [self.ligne_anl.pk]})
        self.assertTrue(Ligne.tous.get(pk=self.ligne_anl.pk).est_supprime)

    def test_admin_refuse_aux_autres_roles(self):
        for user in (self.direction, self.responsable_ooa, self.saisie_ooa):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(self.client.get(self.url).status_code, 302)
