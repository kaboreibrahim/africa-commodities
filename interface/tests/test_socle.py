from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from societes.models import ObjectifMensuel

from .outils import JeuInterfaceMixin


class AccueilTests(JeuInterfaceMixin, TestCase):
    def test_anonyme_redirige_vers_la_connexion(self):
        reponse = self.client.get("/")
        self.assertEqual(reponse.status_code, 302)
        self.assertTrue(reponse.url.startswith(reverse("account_login")))

    def test_admin_et_direction_vont_a_la_vue_groupe(self):
        for user in (self.admin_groupe, self.direction):
            with self.subTest(user=user.username):
                self.connecter(user)
                self.assertRedirects(self.client.get("/"), reverse("interface:groupe"), fetch_redirect_response=False)

    def test_les_autres_vont_a_leur_premiere_societe(self):
        self.connecter(self.saisie_anl)
        self.assertRedirects(self.client.get("/"), reverse("interface:tableau", args=["anl"]),
                             fetch_redirect_response=False)

    def test_sans_societe(self):
        self.connecter(self.affectation_inactive)
        reponse = self.client.get("/")
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "Aucune société ne vous est encore attribuée")


class OngletsTests(JeuInterfaceMixin, TestCase):
    def test_onglets_limites_aux_societes_accessibles(self):
        self.connecter(self.saisie_ooa)
        reponse = self.client.get(reverse("interface:tableau", args=["ooa"]))
        self.assertEqual([s.code for s in reponse.context["onglets"]], ["ooa"])
        self.assertNotContains(reponse, "Vue Groupe")
        self.assertNotContains(reponse, "Africa Newport")

    def test_direction_voit_toutes_les_societes_et_la_vue_groupe(self):
        self.connecter(self.direction)
        reponse = self.client.get(reverse("interface:tableau", args=["ooa"]))
        self.assertEqual(len(reponse.context["onglets"]), 5)
        self.assertContains(reponse, "Vue Groupe")

    def test_coche_quand_l_objectif_est_atteint(self):
        ObjectifMensuel.objects.create(societe=self.ooa, mois=self.ligne_saisie_ooa.date, montant=150_000)
        self.connecter(self.lecture_ooa)
        # Les lignes « SAISIE-OOA » et « COLLEGUE-OOA » du mois font 200 000 F : objectif de 150 000 F atteint.
        reponse = self.client.get(reverse("interface:onglets") + "?actif=ooa", HTTP_HX_REQUEST="true")
        self.assertContains(reponse, "objectif atteint")
        self.assertNotContains(reponse, "<html")
        ObjectifMensuel.objects.update(montant=250_000)
        reponse = self.client.get(reverse("interface:onglets") + "?actif=ooa", HTTP_HX_REQUEST="true")
        self.assertNotContains(reponse, "objectif atteint")

    def test_societe_non_autorisee_404(self):
        self.connecter(self.saisie_anl)
        self.assertEqual(self.client.get(reverse("interface:tableau", args=["ooa"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("interface:tableau", args=["inconnue"])).status_code, 404)

    def test_vue_groupe_404_pour_les_roles_par_societe(self):
        for user in (self.responsable_ooa, self.saisie_ooa, self.lecture_ooa):
            with self.subTest(user=user.username):
                self.connecter(user)
                self.assertEqual(self.client.get(reverse("interface:groupe")).status_code, 404)


class ThemeTests(JeuInterfaceMixin, TestCase):
    def test_theme_societe(self):
        self.connecter(self.saisie_ooa)
        reponse = self.client.get(reverse("interface:theme", args=["ooa"]))
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse["Content-Type"], "text/css; charset=utf-8")
        self.assertIn("max-age=3600", reponse["Cache-Control"])
        css = reponse.content.decode()
        self.assertIn("--c-principale:#1B7A2E", css)
        self.assertIn("--c-claire:#E8F2EA", css)
        self.assertIn(".serie-ooa{--c-serie:#1B7A2E}", css)
        self.assertNotIn("serie-anl", css)  # seulement les sociétés accessibles

    def test_theme_groupe_neutre(self):
        self.connecter(self.direction)
        css = self.client.get(reverse("interface:theme", args=["groupe"])).content.decode()
        self.assertIn("--c-principale:#1A2B4A", css)
        self.assertEqual(css.count(".serie-"), 5)

    def test_theme_non_autorise(self):
        self.connecter(self.saisie_anl)
        self.assertEqual(self.client.get(reverse("interface:theme", args=["ooa"])).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("interface:theme", args=["ooa"])).status_code, 302)

    def test_page_utilise_le_theme_et_le_logo_de_la_societe(self):
        self.connecter(self.saisie_ooa)
        reponse = self.client.get(reverse("interface:tableau", args=["ooa"]))
        self.assertContains(reponse, '/theme/ooa.css"')
        self.assertContains(reponse, "img/logos/ooa.jpg")


class MoisTests(JeuInterfaceMixin, TestCase):
    def test_mois_memorise_en_session(self):
        self.connecter(self.saisie_ooa)
        url = reverse("interface:tableau", args=["ooa"])
        self.assertContains(self.client.get(url + "?mois=2026-03"), "mars 2026")
        self.assertContains(self.client.get(url), "mars 2026")
        reponse = self.client.get(url + "?mois=2026-99")
        self.assertEqual(reponse.status_code, 200)


@override_settings(DEBUG=False)
class PagesErreurTests(JeuInterfaceMixin, TestCase):
    def test_404_en_francais(self):
        self.connecter(self.saisie_anl)
        reponse = self.client.get(reverse("interface:tableau", args=["ooa"]))
        self.assertEqual(reponse.status_code, 404)
        self.assertContains(reponse, "Page introuvable", status_code=404)
        self.assertContains(reponse, "Retour à l'accueil", status_code=404)

    def test_403_en_francais(self):
        self.connecter(self.saisie_ooa)
        with self.assertLogs("securite", "WARNING"):
            reponse = self.client.get(f"/{settings.ADMIN_URL}", follow=True)
        self.assertContains(reponse, "Accès refusé", status_code=403)


class PiedDePageTests(JeuInterfaceMixin, TestCase):
    def test_version_et_regle(self):
        self.connecter(self.lecture_ooa)
        reponse = self.client.get(reverse("interface:tableau", args=["ooa"]))
        self.assertContains(reponse, "version 0.3.0")
        self.assertContains(reponse, "Règle en vigueur")

