"""Livraison 6 : journal de sécurité (admin), page Mon compte, pages d'erreur."""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comptes import services
from comptes.models import JournalSecurite

from .outils import JeuInterfaceMixin
from .test_qualite import AnalyseurCSP

E = JournalSecurite.Evenement


class JournalTests(JeuInterfaceMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("interface:journal")
        services.accorder_acces_societe(self.admin_groupe, self.saisie_anl, self.ooa, "saisie", motif="Remplacement")
        services.modifier_acces_societe(self.admin_groupe, self.saisie_anl.affectations.get(societe=self.ooa), role="lecture")
        JournalSecurite.objects.create(evenement=E.ECHEC_CONNEXION, identifiant_saisi="pirate@exemple.ci", ip="10.0.0.9")

    def test_reserve_a_l_admin_groupe(self):
        self.connecter(self.admin_groupe)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        for utilisateur in (self.responsable_ooa, self.saisie_ooa, self.direction):
            self.connecter(utilisateur)
            with self.assertLogs("securite", "WARNING"):
                self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_evenements_avant_apres_et_familles(self):
        self.connecter(self.admin_groupe)
        reponse = self.client.get(self.url)
        self.assertContains(reponse, "Accès société modifié")
        self.assertContains(reponse, "avant-apres")  # avant / après en deux colonnes
        self.assertContains(reponse, "evenement--alerte")  # échec de connexion
        self.assertContains(reponse, "evenement--droits")
        self.assertContains(reponse, "pirate@exemple.ci")
        self.assertContains(reponse, "(Alerte)")  # la famille est aussi donnée en texte

    def test_filtres(self):
        self.connecter(self.admin_groupe)
        reponse = self.client.get(self.url, {"evenement": E.ECHEC_CONNEXION})
        self.assertEqual([l["e"].evenement for l in reponse.context["lignes"]], [E.ECHEC_CONNEXION])
        reponse = self.client.get(self.url, {"q": "saisie_anl@exemple.ci"})
        lignes = reponse.context["lignes"]
        self.assertTrue(lignes)  # les actions faites SUR cette personne sont retrouvées par son e-mail
        self.assertTrue(all("saisie_anl" in l["e"].details.get("cible_email", "")
                            or (l["e"].utilisateur and "saisie_anl" in l["e"].utilisateur.email) for l in lignes))
        demain = (timezone.localdate() + timedelta(days=1)).isoformat()
        self.assertEqual(len(self.client.get(self.url, {"du": demain}).context["lignes"]), 0)

    def test_export_csv(self):
        self.connecter(self.admin_groupe)
        reponse = self.client.get(self.url, {"format": "csv", "evenement": E.ECHEC_CONNEXION})
        self.assertEqual(reponse["Content-Type"], "text/csv; charset=utf-8")
        lignes = reponse.content.decode("utf-8-sig").splitlines()
        self.assertEqual(lignes[0], "Date;Événement;Utilisateur;Identifiant saisi;Adresse IP;Détails")
        self.assertEqual(len(lignes), 2)
        self.assertIn("pirate@exemple.ci", lignes[1])

    def test_csp_et_menu(self):
        self.connecter(self.admin_groupe)
        reponse = self.client.get(self.url)
        analyseur = AnalyseurCSP()
        analyseur.feed(reponse.content.decode())
        self.assertEqual(analyseur.problemes, [])
        self.assertContains(reponse, f'href="{reverse("interface:journal")}"')
        self.connecter(self.saisie_ooa)
        self.assertNotContains(self.client.get(reverse("interface:mon_compte")), reverse("interface:journal"))


class MonCompteTests(JeuInterfaceMixin, TestCase):
    def test_page_pour_tout_utilisateur_connecte(self):
        for utilisateur in (self.admin_groupe, self.saisie_ooa, self.direction, self.lecture_ooa):
            with self.subTest(utilisateur=utilisateur.username):
                self.connecter(utilisateur)
                reponse = self.client.get(reverse("interface:mon_compte"))
                self.assertEqual(reponse.status_code, 200)
                self.assertContains(reponse, utilisateur.email)
                self.assertContains(reponse, reverse("account_change_password"))

    def test_acces_et_vue_groupe_affiches(self):
        self.connecter(self.saisie_ooa)
        reponse = self.client.get(reverse("interface:mon_compte"))
        self.assertContains(reponse, "OOA · Saisie")
        self.assertContains(reponse, "Aucune habilitation Vue Groupe")
        self.connecter(self.direction)
        self.assertContains(self.client.get(reverse("interface:mon_compte")), "détail autorisé")

    def test_dernieres_connexions_limitees_a_10_et_a_soi(self):
        for i in range(12):
            JournalSecurite.objects.create(utilisateur=self.saisie_ooa, evenement=E.CONNEXION, ip=f"10.0.0.{i}")
        JournalSecurite.objects.create(utilisateur=self.lecture_ooa, evenement=E.CONNEXION, ip="192.168.9.9")
        self.connecter(self.saisie_ooa)
        reponse = self.client.get(reverse("interface:mon_compte"))
        self.assertEqual(len(reponse.context["connexions"]), 10)
        self.assertNotContains(reponse, "192.168.9.9")

    def test_anonyme_redirige(self):
        self.assertEqual(self.client.get(reverse("interface:mon_compte")).status_code, 302)


class PagesErreurTests(JeuInterfaceMixin, TestCase):
    def test_404_avec_logo_et_retour(self):
        self.connecter(self.saisie_ooa)
        reponse = self.client.get("/page-qui-n-existe-pas/")
        self.assertContains(reponse, "logo-groupe", status_code=404)
        self.assertContains(reponse, "Retour à l'accueil", status_code=404)

    def test_500_sans_contexte_ni_base(self):
        from django.template.loader import render_to_string

        html = render_to_string("erreurs/500.html")  # aucun contexte : ne doit rien exiger
        self.assertIn("Une erreur est survenue", html)
        self.assertNotIn("menu-lateral", html)  # n'hérite pas de base.html
        self.assertIn("logo-groupe", html)
