from datetime import date

from django.conf import settings
from django.test import TestCase

from comptes.tests.jeu import JeuUtilisateursMixin, activer_totp
from societes.models import Client, ObjectifMensuel


class AdminSocietesTests(JeuUtilisateursMixin, TestCase):
    """L'admin des clients et des objectifs passe par les services (historique avec l'auteur)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        activer_totp(cls.admin_groupe)

    def setUp(self):
        self.client.force_login(self.admin_groupe)
        self.url = f"/{settings.ADMIN_URL}societes/"

    def test_client_ajout_modification_retrait(self):
        reponse = self.client.post(f"{self.url}client/add/", {"societe": self.ooa.pk, "nom": "  PALMCI  ",
                                                              "telephone": "", "email": ""})
        self.assertEqual(reponse.status_code, 302)
        client = Client.objects.get()
        self.assertEqual(client.nom, "PALMCI")
        self.assertEqual(client.history.first().history_user, self.admin_groupe)

        self.client.post(f"{self.url}client/{client.pk}/change/", {"nom": "PALMCI", "telephone": "0102",
                                                                   "email": ""})
        client.refresh_from_db()
        self.assertEqual(client.telephone, "0102")

        self.client.post(f"{self.url}client/", {"action": "suppression_douce", "_selected_action": [client.pk]})
        self.assertFalse(Client.objects.exists())
        self.assertTrue(Client.tous.get().est_supprime)

    def test_objectif_definition_changement_de_mois_et_suppression(self):
        self.client.post(f"{self.url}objectifmensuel/add/", {"societe": self.ooa.pk, "mois": "15/10/2026",
                                                             "montant": 2_000_000})
        objectif = ObjectifMensuel.objects.get()
        self.assertEqual((objectif.mois, objectif.montant), (date(2026, 10, 1), 2_000_000))
        self.assertEqual(objectif.history.first().history_user, self.admin_groupe)

        self.client.post(f"{self.url}objectifmensuel/{objectif.pk}/change/",
                         {"societe": self.ooa.pk, "mois": "01/11/2026", "montant": 3_000_000})
        self.assertEqual(list(ObjectifMensuel.objects.values_list("mois", "montant")), [(date(2026, 11, 1), 3_000_000)])

        nouveau = ObjectifMensuel.objects.get()
        self.client.post(f"{self.url}objectifmensuel/{nouveau.pk}/delete/", {"post": "yes"})
        self.assertFalse(ObjectifMensuel.objects.exists())

    def test_pages_societe_avec_affectations_et_historique(self):
        self.assertEqual(self.client.get(f"{self.url}societe/{self.ooa.pk}/change/").status_code, 200)
        self.assertEqual(self.client.get(f"{self.url}societe/{self.ooa.pk}/history/").status_code, 200)
        self.assertEqual(self.client.get(f"/{settings.ADMIN_URL}comptes/journalsecurite/").status_code, 200)
        self.assertEqual(self.client.get(f"/{settings.ADMIN_URL}comptes/journalsecurite/add/").status_code, 403)
