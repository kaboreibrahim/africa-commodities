import json
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from comptes.tests.jeu import creer_ligne
from repartition.models import RegleRepartition
from societes.models import Client

from .outils import HTMX, JeuInterfaceMixin, compter_requetes


class ClientsTests(JeuInterfaceMixin, TestCase):
    def url(self, code="ooa"):
        return reverse("interface:clients", args=[code])

    def test_liste_avec_nombre_de_lignes_en_une_requete(self):
        palmci = Client.objects.create(societe=self.ooa, nom="PALMCI")
        Client.objects.create(societe=self.ooa, nom="SIFCA")
        creer_ligne(self.ooa, self.saisie_ooa, client=palmci)
        creer_ligne(self.ooa, self.saisie_ooa, client=palmci).supprimer()  # ligne supprimée : non comptée
        self.connecter(self.lecture_ooa)
        reponse = self.client.get(self.url())
        self.assertEqual({c.nom: c.nb_lignes for c in reponse.context["clients"]}, {"PALMCI": 1, "SIFCA": 0})
        self.assertNotContains(reponse, "+ Ajouter le client")  # lecture seule
        self.assertNotContains(reponse, "Retirer PALMCI")
        with compter_requetes() as compte:
            list(reponse.context["clients"].all())
        self.assertEqual(compte["nombre"], 1)

    def test_ajout_htmx_et_evenement(self):
        self.connecter(self.responsable_ooa)
        reponse = self.client.post(self.url(), {"nom": "  PALMCI  ", "telephone": "0102", "email": ""}, **HTMX)
        self.assertEqual(reponse.status_code, 200)
        self.assertNotContains(reponse, "<html")
        evenements = json.loads(reponse["HX-Trigger"])
        client = Client.objects.get()
        self.assertEqual(evenements["clientsModifies"], {"id": client.pk, "nom": "PALMCI"})
        self.assertEqual(client.history.first().history_user, self.responsable_ooa)

    def test_doublon(self):
        Client.objects.create(societe=self.ooa, nom="PALMCI")
        self.connecter(self.responsable_ooa)
        reponse = self.client.post(self.url(), {"nom": "palmci"}, **HTMX)
        self.assertEqual(reponse.status_code, 422)
        self.assertContains(reponse, "Ce client existe déjà pour cette société.", status_code=422)
        self.assertEqual(Client.objects.count(), 1)

    def test_ajout_rapide_depuis_la_saisie(self):
        self.connecter(self.responsable_ooa)
        page = self.client.get(reverse("interface:lignes", args=["ooa"]))
        self.assertContains(page, 'id="ajout-client-rapide"')
        self.assertContains(page, 'hx-trigger="clientsModifies from:body"')
        reponse = self.client.post(self.url(), {"nom": "SOGB", "rapide": "1"}, **HTMX)
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, 'id="ajout-client-rapide"')
        self.assertIn("clientsModifies", json.loads(reponse["HX-Trigger"]))
        champ = self.client.get(reverse("interface:champ_client", args=["ooa"]) + "?client=", **HTMX)
        self.assertContains(champ, "SOGB")
        self.assertNotContains(champ, "<html")
        # La saisie (sans droit de gestion) n'a pas l'ajout rapide
        self.connecter(self.saisie_ooa)
        self.assertNotContains(self.client.get(reverse("interface:lignes", args=["ooa"])), 'id="ajout-client-rapide"')

    def test_modifier_et_retirer(self):
        client = Client.objects.create(societe=self.ooa, nom="PALMCI")
        ligne = creer_ligne(self.ooa, self.saisie_ooa, client=client)
        self.connecter(self.responsable_ooa)
        page = self.client.get(self.url())
        self.assertContains(page, "PALMCI est utilisé dans 1 ligne(s), les lignes existantes ne changent pas.")
        url = reverse("interface:client_modifier", args=["ooa", client.pk])
        self.assertContains(self.client.get(url, **HTMX), 'id="modif_client_nom"')
        reponse = self.client.post(url, {"nom": "PALMCI SA", "telephone": "", "email": "contact@palmci.ci"}, **HTMX)
        self.assertEqual(reponse.status_code, 204)
        client.refresh_from_db()
        self.assertEqual((client.nom, client.email), ("PALMCI SA", "contact@palmci.ci"))
        reponse = self.client.post(reverse("interface:client_retirer", args=["ooa", client.pk]), **HTMX)
        self.assertEqual(reponse.status_code, 200)
        self.assertTrue(Client.tous.get(pk=client.pk).est_supprime)
        ligne.refresh_from_db()
        self.assertEqual(ligne.client_id, client.pk)  # la ligne garde son client

    def test_droits(self):
        client = Client.objects.create(societe=self.ooa, nom="PALMCI")
        for user, statut in ((self.saisie_ooa, 403), (self.lecture_ooa, 403), (self.direction, 403),
                             (self.saisie_anl, 404)):
            with self.subTest(user=user.username):
                self.connecter(user)
                with self.assertLogs("securite", "WARNING"):
                    self.assertEqual(self.client.post(self.url(), {"nom": "X"}).status_code, statut)
                with self.assertLogs("securite", "WARNING"):
                    url = reverse("interface:client_retirer", args=["ooa", client.pk])
                    self.assertEqual(self.client.post(url).status_code, statut)
        self.assertEqual(Client.objects.count(), 1)
        self.connecter(self.admin_groupe)  # client d'OOA demandé sous l'adresse d'ANL
        self.assertEqual(self.client.get(reverse("interface:client_modifier", args=["anl", client.pk])).status_code, 404)

    def test_sans_javascript(self):
        self.connecter(self.admin_groupe)
        reponse = self.client.post(self.url(), {"nom": "PALMCI"})
        self.assertRedirects(reponse, self.url(), fetch_redirect_response=False)
        reponse = self.client.post(self.url(), {"nom": "palmci"})
        self.assertContains(reponse, "Ce client existe déjà", status_code=422)
        self.assertContains(reponse, "<html", status_code=422)


class RegleTests(JeuInterfaceMixin, TestCase):
    def test_page_en_lecture_pour_tous(self):
        for user in (self.lecture_ooa, self.saisie_anl, self.direction):
            with self.subTest(user=user.username):
                self.connecter(user)
                reponse = self.client.get(reverse("interface:regle"))
                self.assertEqual(reponse.status_code, 200)
                self.assertContains(reponse, "les lignes déjà enregistrées gardent la répartition")
                self.assertNotContains(reponse, "Créer une nouvelle règle")
        exemples = reponse.context["exemples"]
        self.assertEqual((exemples[0].charges, exemples[0].africa_commodities, exemples[0].comptes), (25_000, 45_000, 10_000))
        self.assertEqual((exemples[1].charges, exemples[1].africa_commodities, exemples[1].risques),
                         (1_250_000, 2_250_000, 500_000))

    def test_lien_admin_pour_l_admin_groupe(self):
        self.connecter(self.admin_groupe)
        self.assertContains(self.client.get(reverse("interface:regle")), "Créer une nouvelle règle")

    def test_historique_et_cache_de_la_regle(self):
        self.connecter(self.lecture_ooa)
        self.client.get(reverse("interface:regle"))  # met la règle en cache
        RegleRepartition.objects.create(date_debut=date(2026, 1, 2), pct_charges=Decimal("30"), note="Décision du CA")
        reponse = self.client.get(reverse("interface:regle"))
        self.assertEqual(reponse.context["regle"].pct_charges, 30)  # le cache a été oublié
        self.assertContains(reponse, "Décision du CA")
        self.assertGreaterEqual(len(reponse.context["regles"]), 2)
