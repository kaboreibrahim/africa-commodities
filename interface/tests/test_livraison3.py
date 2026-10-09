from django.test import TestCase
from django.urls import reverse

from societes.models import Client

from .outils import HTMX, JeuInterfaceMixin


class RechercheClientsTests(JeuInterfaceMixin, TestCase):
    def test_recherche_filtre_les_clients(self):
        Client.objects.create(societe=self.ooa, nom="PALMCI", email="contact@palmci.ci")
        Client.objects.create(societe=self.ooa, nom="SIFCA", telephone="0707")
        self.connecter(self.responsable_ooa)
        url = reverse("interface:clients", args=["ooa"])
        reponse = self.client.get(url, {"q": "palm"}, **HTMX)
        self.assertContains(reponse, "PALMCI")
        self.assertNotContains(reponse, "SIFCA")
        self.assertContains(self.client.get(url, {"q": "zzz"}), "Aucun client ne correspond")
        self.assertContains(self.client.get(url), "vue-cartes")  # version cartes pour le téléphone


class ListeLignesTests(JeuInterfaceMixin, TestCase):
    def test_cartes_et_etat_vide(self):
        self.connecter(self.saisie_ooa)
        url = reverse("interface:lignes", args=["ooa"])
        reponse = self.client.get(url)
        self.assertContains(reponse, "carte-ligne")
        self.assertContains(reponse, "Voir la répartition")
        reponse = self.client.get(url, {"q": "introuvable-xyz"})
        self.assertContains(reponse, "Aucun enregistrement pour cette période")
        self.assertContains(reponse, "etat-vide")
