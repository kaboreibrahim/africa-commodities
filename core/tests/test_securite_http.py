import io
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from comptes import checks
from comptes.axes import ip_client
from societes.models import Societe

RACINE = Path(settings.BASE_DIR)


def image(format_pil: str, nom: str) -> SimpleUploadedFile:
    tampon = io.BytesIO()
    Image.new("RGB", (8, 8), "green").save(tampon, format=format_pil)
    return SimpleUploadedFile(nom, tampon.getvalue())


class EnTetesTests(TestCase):
    def test_en_tetes_de_la_page_de_connexion(self):
        reponse = self.client.get(reverse("account_login"))
        self.assertEqual(reponse.status_code, 200)
        csp = reponse.headers["Content-Security-Policy"]
        for directive in ("default-src 'self'", "script-src 'self'", "style-src 'self'", "object-src 'none'",
                          "frame-ancestors 'none'", "form-action 'self'", "base-uri 'self'"):
            self.assertIn(directive, csp)
        self.assertNotIn("unsafe-inline", csp)
        self.assertNotIn("unsafe-eval", csp)
        self.assertEqual(reponse.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(reponse.headers["Referrer-Policy"], "same-origin")
        self.assertEqual(reponse.headers["X-Frame-Options"], "DENY")
        self.assertEqual(reponse.headers["Cross-Origin-Opener-Policy"], "same-origin")
        self.assertEqual(reponse.headers["Permissions-Policy"], "camera=(), microphone=(), geolocation=(), payment=()")

    def test_aucun_cdn_ni_script_inline_dans_les_gabarits(self):
        for gabarit in (RACINE / "templates").rglob("*.html"):
            contenu = gabarit.read_text(encoding="utf-8")
            with self.subTest(gabarit=gabarit.name):
                # Seuls les scripts externes (src=) ou de données (application/json) sont permis.
                for balise in re.findall(r"<script\b[^>]*>", contenu):
                    self.assertTrue("src=" in balise or "application/json" in balise, balise)
                self.assertNotIn("style=", contenu)
                self.assertNotIn("<style", contenu)
                self.assertNotRegex(contenu, r"\son[a-z]+=")
                self.assertNotIn("hx-on", contenu)
                self.assertNotIn("//cdn", contenu)
                self.assertNotIn("https://", contenu)


class LogoTests(TestCase):
    def setUp(self):
        self.ooa = Societe.objects.get(code="ooa")

    def valider(self, fichier):
        self.ooa.logo = fichier
        self.ooa.full_clean()

    def test_png_jpeg_webp_acceptes(self):
        for format_pil, nom in (("PNG", "logo.png"), ("JPEG", "logo.jpg"), ("WEBP", "logo.webp")):
            with self.subTest(format=format_pil):
                self.valider(image(format_pil, nom))

    def test_svg_refuse(self):
        svg = SimpleUploadedFile("logo.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
        with self.assertRaises(ValidationError) as e:
            self.valider(svg)
        self.assertIn("logo", e.exception.message_dict)

    def test_faux_png_refuse(self):
        with self.assertRaises(ValidationError) as e:
            self.valider(SimpleUploadedFile("logo.png", b"ceci est un simple fichier texte"))
        self.assertIn("pas une image valide", " ".join(e.exception.message_dict["logo"]))

    def test_gif_renomme_en_png_refuse(self):
        with self.assertRaises(ValidationError):
            self.valider(image("GIF", "logo.png"))

    def test_fichier_trop_lourd_refuse(self):
        lourd = image("PNG", "logo.png")
        lourd.size = 3 * 1024 * 1024
        with self.assertRaises(ValidationError) as e:
            self.valider(lourd)
        self.assertIn("2 Mo", " ".join(e.exception.message_dict["logo"]))


class IpClientTests(SimpleTestCase):
    def requete(self, **meta):
        return RequestFactory().get("/", REMOTE_ADDR="10.0.0.2", **meta)

    def test_sans_proxy_remote_addr(self):
        self.assertEqual(ip_client(self.requete(HTTP_X_FORWARDED_FOR="6.6.6.6")), "10.0.0.2")

    @override_settings(NB_PROXYS_DE_CONFIANCE=1)
    def test_derriere_nginx_adresse_ajoutee_par_le_proxy(self):
        self.assertEqual(ip_client(self.requete(HTTP_X_FORWARDED_FOR="203.0.113.7")), "203.0.113.7")
        # Une adresse inventée par le client (à gauche) est ignorée.
        self.assertEqual(ip_client(self.requete(HTTP_X_FORWARDED_FOR="6.6.6.6, 203.0.113.7")), "203.0.113.7")
        self.assertEqual(ip_client(self.requete()), "10.0.0.2")


class VerificationsSystemeTests(TestCase):
    def test_w001_admin_sans_totp(self):
        from comptes.models import Utilisateur
        from comptes.tests.jeu import activer_totp

        self.assertEqual(checks.verifier_mfa_administrateurs(None), [])
        admin = Utilisateur.objects.create_user("adm", "adm@exemple.ci", "x", role_global="admin_groupe")
        self.assertEqual([c.id for c in checks.verifier_mfa_administrateurs(None)], ["comptes.W001"])
        activer_totp(admin)
        self.assertEqual(checks.verifier_mfa_administrateurs(None), [])

    def test_w002_url_admin(self):
        with override_settings(ADMIN_URL="admin/"):
            self.assertEqual([c.id for c in checks.verifier_url_admin(None)], ["comptes.W002"])
        self.assertEqual(checks.verifier_url_admin(None), [])

    def test_e001_backend_axes_en_premier(self):
        self.assertEqual(checks.verifier_backend_axes(None), [])
        with override_settings(AUTHENTICATION_BACKENDS=["django.contrib.auth.backends.ModelBackend",
                                                        checks.BACKEND_AXES]):
            self.assertEqual([c.id for c in checks.verifier_backend_axes(None)], ["comptes.E001"])


class CheckDeployTests(SimpleTestCase):
    """`check --deploy` avec les réglages de production et des variables valides : aucune erreur."""

    def lancer(self, **variables):
        env = {**os.environ, "DJANGO_SECRET_KEY": secrets.token_urlsafe(60), "DJANGO_ALLOWED_HOSTS": "marges.exemple.ci",
               "DATABASE_URL": "postgres://verif:verif@127.0.0.1:1/verif?connect_timeout=2", "DJANGO_DEBUG": "False", **variables}
        return subprocess.run(  # nosec B603 : commande fixe, sans shell
            [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "ERROR",
             "--settings=config.settings.prod"],
            cwd=RACINE, env=env, capture_output=True, text=True, timeout=120,
        )

    def test_check_deploy_sans_erreur(self):
        resultat = self.lancer()
        self.assertEqual(resultat.returncode, 0, resultat.stderr + resultat.stdout)
        self.assertNotIn("ERRORS", resultat.stderr + resultat.stdout)
        # Seuls avertissements tolérés : ceux du projet (W001 / W002), jamais ceux de Django.
        self.assertNotIn("security.W", resultat.stderr + resultat.stdout)

    def test_garde_fous_de_production(self):
        for variables, message in (({"DJANGO_SECRET_KEY": "trop-courte"}, "50 caract"),
                                   ({"DATABASE_URL": "sqlite:///x.sqlite3"}, "SQLite"),
                                   ({"DJANGO_ALLOWED_HOSTS": ""}, "DJANGO_ALLOWED_HOSTS")):
            with self.subTest(message=message):
                resultat = self.lancer(**variables)
                self.assertNotEqual(resultat.returncode, 0)
                self.assertIn("ImproperlyConfigured", resultat.stderr)
