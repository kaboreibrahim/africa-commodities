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


class NavigationTests(JeuInterfaceMixin, TestCase):
    def test_menu_vers_le_tableau_de_bord_avec_logos(self):
        self.connecter(self.admin_groupe)
        reponse = self.client.get(reverse("interface:lignes", args=["ooa"]))
        for code in ("ooa", "anl"):  # un clic sur une société ouvre directement son tableau de bord, même depuis les dossiers
            self.assertContains(reponse, f'href="{reverse("interface:tableau", args=[code])}"')
        self.assertContains(reponse, 'class="onglet__logo"')
        self.assertNotContains(reponse, ">Tableau de bord<")

    def test_bouton_voir_les_dossiers_et_fenetre_de_saisie(self):
        self.connecter(self.saisie_ooa)
        tableau = self.client.get(reverse("interface:tableau", args=["ooa"]))
        self.assertContains(tableau, f'href="{reverse("interface:lignes", args=["ooa"])}"')
        self.assertContains(tableau, "Voir les dossiers")
        liste = self.client.get(reverse("interface:lignes", args=["ooa"]))
        self.assertContains(liste, 'id="dialogue-saisie"')
        self.assertContains(liste, "Nouveau dossier")
        self.connecter(self.lecture_ooa)  # pas de droit de saisie : ni bouton ni fenêtre
        self.assertNotContains(self.client.get(reverse("interface:lignes", args=["ooa"])), "dialogue-saisie")
        reponse = self.client.get(reverse("interface:lignes", args=["ooa"]), {"nouveau": "1"})
        self.assertNotContains(reponse, "form-ligne")
