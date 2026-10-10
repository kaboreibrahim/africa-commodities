"""Pages d'authentification (connexion, code à 6 chiffres, compte bloqué) : contenu, sécurité, CSP."""
import re
from html.parser import HTMLParser
from pathlib import Path

from django.test import TestCase
from django.urls import reverse

from .jeu import MOT_DE_PASSE, JeuUtilisateursMixin, ReinitialiserAxesMixin, activer_totp

URL_CONNEXION = reverse("account_login")
MESSAGE_ECHEC = "Adresse e-mail ou mot de passe incorrect."


class AnalyseurCSP(HTMLParser):
    """Relève tout ce qu'une CSP « 'self' » sans 'unsafe-inline' bloquerait."""

    def __init__(self):
        super().__init__()
        self.problemes = []

    def handle_starttag(self, balise, attributs):
        attrs = dict(attributs)
        for nom in attrs:
            if nom == "style" or re.fullmatch(r"on[a-z]+", nom):
                self.problemes.append(f"{nom} sur <{balise}>")
        if balise == "style":
            self.problemes.append("<style> inline")
        if balise == "script" and "src" not in attrs and attrs.get("type") != "application/json":
            self.problemes.append("<script> inline")
        lien = attrs.get("src") or attrs.get("href") or ""
        if balise in ("script", "link", "img") and re.match(r"^(https?:)?//", lien):
            self.problemes.append(f"ressource externe : {lien}")


class PagesAuthTests(ReinitialiserAxesMixin, JeuUtilisateursMixin, TestCase):
    def verifier_csp(self, reponse):
        analyseur = AnalyseurCSP()
        analyseur.feed(reponse.content.decode())
        self.assertEqual(analyseur.problemes, [])

    def echec(self):
        return self.client.post(URL_CONNEXION, {"login": self.saisie_ooa.email, "password": "mauvais-mot-de-passe"})

    def test_connexion_champs_et_logo(self):
        reponse = self.client.get(URL_CONNEXION)
        self.assertEqual(reponse.status_code, 200)
        html = reponse.content.decode()
        self.assertIn("logo-groupe", html)
        self.assertIn('autocomplete="username"', html)
        self.assertIn('autocomplete="current-password"', html)
        self.assertIn("csrfmiddlewaretoken", html)
        self.assertIn("data-rideau", html)  # rideau actif sur un affichage neuf
        self.assertNotIn("Se souvenir de moi", html)
        self.assertNotIn("Créer un compte", html)
        self.verifier_csp(reponse)

    def test_erreur_generique_sans_rideau(self):
        reponse = self.echec()
        html = reponse.content.decode()
        self.assertEqual(reponse.status_code, 200)
        self.assertIn(MESSAGE_ECHEC, html)
        self.assertIn('aria-invalid="true"', html)
        self.assertNotIn("data-rideau", html)
        self.assertNotIn('class="rideau', html)
        self.assertNotIn("mauvais-mot-de-passe", html)  # le mot de passe n'est jamais renvoyé
        self.verifier_csp(reponse)

    def test_message_identique_pour_compte_inexistant(self):
        inconnu = self.client.post(URL_CONNEXION, {"login": "personne@exemple.ci", "password": "x" * 14})
        connu = self.echec()
        corps = lambda r: re.sub(r"csrfmiddlewaretoken\" value=\"\w+\"", "", r.content.decode())  # noqa: E731
        for reponse in (inconnu, connu):
            self.assertIn(MESSAGE_ECHEC, reponse.content.decode())
        self.assertEqual(corps(inconnu).count("alerte--erreur"), corps(connu).count("alerte--erreur"))

    def test_page_2fa(self):
        activer_totp(self.responsable_ooa)
        self.client.post(URL_CONNEXION, {"login": self.responsable_ooa.email, "password": MOT_DE_PASSE})
        reponse = self.client.get(reverse("mfa_authenticate"))
        self.assertEqual(reponse.status_code, 200)
        html = reponse.content.decode()
        for attendu in ('autocomplete="one-time-code"', 'inputmode="numeric"', 'maxlength="6"', 'name="code"',
                        "Étape 2 sur 2", "Code de vérification à 6 chiffres"):
            self.assertIn(attendu, html)
        self.assertNotIn("data-rideau", html)
        self.verifier_csp(reponse)

    def test_page_2fa_code_de_recuperation(self):
        activer_totp(self.responsable_ooa)
        self.client.post(URL_CONNEXION, {"login": self.responsable_ooa.email, "password": MOT_DE_PASSE})
        reponse = self.client.get(reverse("mfa_authenticate") + "?mode=recuperation")
        self.assertContains(reponse, "Code de récupération")
        self.assertNotContains(reponse, 'maxlength="6"')

    def test_code_incorrect_message_generique(self):
        activer_totp(self.responsable_ooa)
        self.client.post(URL_CONNEXION, {"login": self.responsable_ooa.email, "password": MOT_DE_PASSE})
        reponse = self.client.post(reverse("mfa_authenticate"), {"code": "000000"})
        self.assertContains(reponse, "Code incorrect ou expiré. Réessayez avec le code actuel.")
        self.assertContains(reponse, 'role="alert"')
        self.assertNotContains(reponse, "000000")

    def test_compte_bloque_apres_5_echecs(self):
        for _ in range(5):
            self.echec()
        reponse = self.echec()
        self.assertEqual(reponse.status_code, 429)
        self.assertTemplateUsed(reponse, "comptes/compte_bloque.html")
        self.assertContains(reponse, "Accès temporairement suspendu", status_code=429)
        self.assertContains(reponse, "30 minutes", status_code=429)
        self.verifier_csp(reponse)

    def test_pages_de_compte_connecte(self):
        self.client.force_login(self.saisie_ooa)
        for nom in ("account_change_password", "account_logout"):
            with self.subTest(page=nom):
                reponse = self.client.get(reverse(nom))
                self.assertEqual(reponse.status_code, 200)
                self.verifier_csp(reponse)

    def test_activation_totp_et_codes_de_recuperation(self):
        self.client.post(URL_CONNEXION, {"login": self.admin_groupe.email, "password": MOT_DE_PASSE})
        reponse = self.client.get(reverse("mfa_activate_totp"))
        self.assertContains(reponse, 'autocomplete="one-time-code"')
        self.assertContains(reponse, "Installer une application")
        self.verifier_csp(reponse)

    def test_aucun_code_ni_mot_de_passe_dans_le_stockage_navigateur(self):
        racine = Path(__file__).resolve().parents[2] / "static" / "js"
        for nom in ("otp.js", "auth.js", "connexion.js"):
            source = (racine / nom).read_text(encoding="utf-8")
            with self.subTest(fichier=nom):
                self.assertNotIn("localStorage", source)
                self.assertNotIn("console.", source)
