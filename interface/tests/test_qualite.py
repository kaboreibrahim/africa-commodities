"""
Contrôles transversaux de l'interface (lot 3.7) :
- matrice d'accès par rôle sur chaque route principale ;
- compatibilité CSP du HTML réellement rendu (pages complètes et fragments HTMX).
"""
import re
from html.parser import HTMLParser

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from societes.models import Client, DepenseMensuelle

from .outils import HTMX, JeuInterfaceMixin


def routes_societe(code, ligne_pk, client_pk):
    return {
        "tableau": reverse("interface:tableau", args=[code]),
        "lignes": reverse("interface:lignes", args=[code]),
        "apercu": reverse("interface:apercu", args=[code]) + "?quantite=1&marge_unitaire=1000",
        "clients": reverse("interface:clients", args=[code]),
        "corbeille": reverse("interface:corbeille", args=[code]),
        "objectif": reverse("interface:objectif", args=[code]),
        "depenses": reverse("interface:depenses", args=[code]),
        "ligne_modifier": reverse("interface:ligne_modifier", args=[code, ligne_pk]),
        "client_modifier": reverse("interface:client_modifier", args=[code, client_pk]),
    }


class MatriceAccesEcransTests(JeuInterfaceMixin, TestCase):
    """Chaque écran respecte la matrice des droits de l'étape 2."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.client_ooa = Client.objects.create(societe=cls.ooa, nom="PALMCI")
        cls.routes = routes_societe("ooa", cls.ligne_saisie_ooa.pk, cls.client_ooa.pk)

    def statut(self, url, methode="get"):
        try:
            with self.assertLogs("securite", "WARNING"):
                reponse = getattr(self.client, methode)(url)
        except AssertionError:  # aucun refus journalisé
            reponse = getattr(self.client, methode)(url)
        return reponse.status_code

    def test_anonyme_redirige_vers_la_connexion(self):
        for nom, url in {**self.routes, "groupe": reverse("interface:groupe"), "regle": reverse("interface:regle"),
                         "accueil": "/"}.items():
            with self.subTest(route=nom):
                reponse = self.client.get(url)
                self.assertEqual(reponse.status_code, 302)
                self.assertTrue(reponse.url.startswith(reverse("account_login")))

    def test_sans_acces_404(self):
        self.connecter(self.saisie_anl)
        for nom, url in self.routes.items():
            with self.subTest(route=nom):
                self.assertEqual(self.statut(url), 404)
                self.assertIn(self.statut(url, "post"), (404, 405))

    def test_get_selon_le_role(self):
        attendus = {
            # route : rôles qui obtiennent 200 en GET (les autres lecteurs d'OOA : 403)
            "tableau": {"admin_groupe", "direction", "responsable_ooa", "saisie_ooa", "lecture_ooa"},
            "lignes": {"admin_groupe", "direction", "responsable_ooa", "saisie_ooa", "lecture_ooa"},
            "apercu": {"admin_groupe", "direction", "responsable_ooa", "saisie_ooa", "lecture_ooa"},
            "clients": {"admin_groupe", "direction", "responsable_ooa", "saisie_ooa", "lecture_ooa"},
            "corbeille": {"admin_groupe", "responsable_ooa"},
            "objectif": {"admin_groupe", "responsable_ooa"},
            "depenses": {"admin_groupe", "responsable_ooa"},
            "ligne_modifier": {"admin_groupe", "responsable_ooa", "saisie_ooa"},
            "client_modifier": {"admin_groupe", "responsable_ooa"},
        }
        for role in ("admin_groupe", "direction", "responsable_ooa", "saisie_ooa", "lecture_ooa"):
            self.connecter(getattr(self, role))
            for nom, url in self.routes.items():
                with self.subTest(role=role, route=nom):
                    self.assertEqual(self.statut(url), 200 if role in attendus[nom] else 403)

    def test_lecture_aucun_post_accepte(self):
        self.connecter(self.lecture_ooa)
        for nom, url in self.routes.items():
            if nom == "apercu":
                continue
            with self.subTest(route=nom):
                self.assertIn(self.statut(url, "post"), (403, 404, 405))

    def test_vue_groupe_et_regle(self):
        for role, statut in (("admin_groupe", 200), ("direction", 200), ("responsable_ooa", 404),
                             ("saisie_ooa", 404), ("lecture_ooa", 404)):
            with self.subTest(role=role):
                self.connecter(getattr(self, role))
                self.assertEqual(self.statut(reverse("interface:groupe")), statut)
                self.assertEqual(self.client.get(reverse("interface:regle")).status_code, 200)

    def test_direction_ne_voit_aucun_formulaire_de_saisie(self):
        self.connecter(self.direction)
        for nom in ("tableau", "lignes", "clients"):
            with self.subTest(route=nom):
                contenu = self.client.get(self.routes[nom]).content.decode()
                self.assertNotIn('method="post"', contenu.replace('action="/compte/logout/"', ""))


class AnalyseurCSP(HTMLParser):
    """Relève tout ce qu'une CSP « 'self' » sans 'unsafe-inline' bloquerait."""

    def __init__(self):
        super().__init__()
        self.problemes = []
        self.dans_script = False

    def handle_starttag(self, balise, attributs):
        attrs = dict(attributs)
        for nom in attrs:
            if nom == "style":
                self.problemes.append(f"attribut style sur <{balise}>")
            if re.fullmatch(r"on[a-z]+", nom):
                self.problemes.append(f"gestionnaire {nom}= sur <{balise}>")
            if nom.startswith("hx-on"):
                self.problemes.append(f"{nom} sur <{balise}>")
        if balise == "style":
            self.problemes.append("balise <style> inline")
        if balise == "script" and "src" not in attrs and attrs.get("type") != "application/json":
            self.problemes.append("<script> inline")
        if balise in ("script", "link", "img") and re.match(r"^(https?:)?//", attrs.get("src") or attrs.get("href") or ""):
            self.problemes.append(f"ressource externe sur <{balise}>")


class CSPRenduTests(JeuInterfaceMixin, TestCase):
    def analyser(self, reponse):
        analyseur = AnalyseurCSP()
        analyseur.feed(reponse.content.decode())
        return analyseur.problemes

    def test_pages_et_fragments(self):
        DepenseMensuelle.objects.create(societe=self.ooa, mois=self.ligne_saisie_ooa.date, montant=10)
        client = Client.objects.create(societe=self.ooa, nom="PALMCI")
        routes = routes_societe("ooa", self.ligne_saisie_ooa.pk, client.pk)
        pages = [*routes.values(), reverse("interface:groupe"), reverse("interface:regle"),
                 reverse("interface:onglets") + "?actif=ooa", reverse("account_change_password"),
                 reverse("mfa_index"), f"/{settings.ADMIN_URL}"]
        self.connecter(self.admin_groupe)
        for url in pages:
            for entetes in ({}, HTMX):
                with self.subTest(url=url, htmx=bool(entetes)):
                    reponse = self.client.get(url, **entetes)
                    self.assertIn(reponse.status_code, (200, 302))
                    if reponse.status_code == 200 and "html" in reponse.get("Content-Type", ""):
                        self.assertEqual(self.analyser(reponse), [])
        self.client.logout()
        self.assertEqual(self.analyser(self.client.get(reverse("account_login"))), [])

    def test_l_analyseur_detecte_les_violations(self):
        analyseur = AnalyseurCSP()
        analyseur.feed('<div style="x"></div><script>alert(1)</script><a onclick="x" hx-on:click="y"></a>'
                       '<script type="application/json">{}</script><script src="/static/a.js"></script>'
                       '<script src="https://cdn.exemple.com/x.js"></script>')
        self.assertEqual(len(analyseur.problemes), 5)
