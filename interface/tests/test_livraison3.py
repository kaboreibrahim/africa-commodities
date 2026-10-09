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
    def test_liste_et_etat_vide(self):
        self.connecter(self.saisie_ooa)
        url = reverse("interface:lignes", args=["ooa"])
        reponse = self.client.get(url)
        self.assertContains(reponse, "Détail")
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


class DetailEtPdfTests(JeuInterfaceMixin, TestCase):
    def test_detail_d_une_ligne(self):
        self.connecter(self.lecture_ooa)
        reponse = self.client.get(reverse("interface:ligne_detail", args=["ooa", self.ligne_saisie_ooa.pk]))
        self.assertContains(reponse, "Répartition de la marge")
        self.assertContains(reponse, "Télécharger le récapitulatif (PDF)")
        self.assertNotContains(reponse, ">Modifier<")  # lecture seule

    def test_liste_avec_liens_detail_et_pdf_sans_cartes_en_double(self):
        self.connecter(self.saisie_ooa)
        reponse = self.client.get(reverse("interface:lignes", args=["ooa"]))
        self.assertContains(reponse, reverse("interface:ligne_detail", args=["ooa", self.ligne_saisie_ooa.pk]))
        self.assertContains(reponse, reverse("interface:lignes_pdf", args=["ooa"]))
        self.assertNotContains(reponse, "carte-ligne")

    def test_pdf_ligne_et_recapitulatif(self):
        self.connecter(self.lecture_ooa)
        pdf_ligne = self.client.get(reverse("interface:ligne_pdf", args=["ooa", self.ligne_saisie_ooa.pk]))
        self.assertEqual(pdf_ligne["Content-Type"], "application/pdf")
        self.assertTrue(pdf_ligne.content.startswith(b"%PDF"))
        self.assertIn("attachment", pdf_ligne["Content-Disposition"])
        self.assertEqual(pdf_ligne["Cache-Control"], "private, no-store")
        recap = self.client.get(reverse("interface:lignes_pdf", args=["ooa"]))
        self.assertTrue(recap.content.startswith(b"%PDF"))
        self.assertIn("ooa-recap-", recap["Content-Disposition"])
        vide = self.client.get(reverse("interface:lignes_pdf", args=["ooa"]), {"q": "introuvable-xyz"})
        self.assertTrue(vide.content.startswith(b"%PDF"))

    def test_pdf_hors_perimetre_404(self):
        self.connecter(self.saisie_anl)
        self.assertEqual(self.client.get(reverse("interface:ligne_pdf", args=["ooa", self.ligne_saisie_ooa.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("interface:lignes_pdf", args=["ooa"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("interface:ligne_detail", args=["ooa", self.ligne_saisie_ooa.pk])).status_code, 404)


class BoutonsDeLaSocieteTests(JeuInterfaceMixin, TestCase):
    def test_boutons_clients_et_corbeille_a_cote_de_voir_les_dossiers(self):
        self.connecter(self.responsable_ooa)
        for nom in ("tableau", "lignes", "clients", "corbeille"):
            with self.subTest(page=nom):
                reponse = self.client.get(reverse(f"interface:{nom}", args=["ooa"]))
                self.assertContains(reponse, 'aria-label="Pages de Oils of Africa"')
                self.assertContains(reponse, f'href="{reverse("interface:clients", args=["ooa"])}"')
                self.assertContains(reponse, f'href="{reverse("interface:corbeille", args=["ooa"])}"')
        # plus de boutons Dossiers / Clients / Corbeille dans le menu de gauche
        menu = self.client.get(reverse("interface:tableau", args=["ooa"])).content.decode().split('id="menu-lateral"')[1].split("</aside>")[0]
        self.assertNotIn("Corbeille", menu)
        self.assertNotIn("Clients", menu)
        self.assertNotIn("Dossiers", menu)

    def test_pas_de_corbeille_sans_droit_de_gestion(self):
        self.connecter(self.saisie_ooa)
        self.assertNotContains(self.client.get(reverse("interface:tableau", args=["ooa"])),
                               reverse("interface:corbeille", args=["ooa"]))
