from datetime import date
from decimal import Decimal

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import RequestFactory, SimpleTestCase

from core.templatetags.format_fr import fcfa, fcfa_court, iso_mois, mois_long, nombre, pct
from interface.periode import decaler, lire_mois, mois_courant, mois_depuis_requete
from interface.theme import couleur_claire

FINE = " "   # séparateur des milliers
INS = " "    # espace insécable avant l'unité


class FiltresTests(SimpleTestCase):
    def test_fcfa(self):
        self.assertEqual(fcfa(1250000), f"1{FINE}250{FINE}000{INS}F")
        self.assertEqual(fcfa(Decimal("999")), f"999{INS}F")
        self.assertEqual(fcfa(0), f"0{INS}F")
        self.assertEqual(fcfa(-1500), f"-1{FINE}500{INS}F")
        self.assertEqual(fcfa(Decimal("1000.5")), f"1{FINE}001{INS}F")  # arrondi au franc
        self.assertEqual(fcfa(None), "")
        self.assertEqual(fcfa("abc"), "")
        self.assertEqual(nombre(4800000), f"4{FINE}800{FINE}000")

    def test_fcfa_court(self):
        self.assertEqual(fcfa_court(4_800_000), f"4,8{INS}M")
        self.assertEqual(fcfa_court(1_000_000), f"1{INS}M")
        self.assertEqual(fcfa_court(12_350_000), f"12,4{INS}M")
        self.assertEqual(fcfa_court(250_000), f"250{INS}k")
        self.assertEqual(fcfa_court(1_500), f"2{INS}k")
        self.assertEqual(fcfa_court(800), "800")
        self.assertEqual(fcfa_court(None), "")

    def test_pct(self):
        self.assertEqual(pct(2.5), f"2,5{INS}%")
        self.assertEqual(pct(25.0), f"25{INS}%")
        self.assertEqual(pct(Decimal("33.333")), f"33,3{INS}%")
        self.assertEqual(pct(Decimal("99.96")), f"100{INS}%")
        self.assertEqual(pct(0), f"0{INS}%")
        self.assertEqual(pct(None), "")

    def test_mois(self):
        self.assertEqual(mois_long(date(2026, 10, 1)), "octobre 2026")
        self.assertEqual(mois_long(date(2027, 2, 14)), "février 2027")
        self.assertEqual(mois_long("2026-10"), "")
        self.assertEqual(iso_mois(date(2026, 3, 1)), "2026-03")


class PeriodeTests(SimpleTestCase):
    def requete(self, **get):
        requete = RequestFactory().get("/", get)
        requete.session = SessionStore()
        return requete

    def test_lire_mois(self):
        self.assertEqual(lire_mois("2026-10"), date(2026, 10, 1))
        for invalide in ("2026-13", "2026-00", "26-10", "2026-1", "abcd-ef", "", None, "1999-12", "2026-10-01",
                         "<script>"):
            with self.subTest(valeur=invalide):
                self.assertIsNone(lire_mois(invalide))

    def test_mois_depuis_requete_et_session(self):
        requete = self.requete(mois="2026-07")
        self.assertEqual(mois_depuis_requete(requete), date(2026, 7, 1))
        suivante = self.requete()
        suivante.session = requete.session  # même session : le mois est mémorisé
        self.assertEqual(mois_depuis_requete(suivante), date(2026, 7, 1))

    def test_valeur_invalide_donne_le_mois_courant(self):
        for invalide in ("2026-13", "n'importe quoi", "", "2026-1"):
            with self.subTest(valeur=invalide):
                self.assertEqual(mois_depuis_requete(self.requete(mois=invalide)), mois_courant())

    def test_par_defaut_mois_courant(self):
        self.assertEqual(mois_depuis_requete(self.requete()), mois_courant())

    def test_decaler(self):
        self.assertEqual(decaler(date(2026, 1, 1), -1), date(2025, 12, 1))
        self.assertEqual(decaler(date(2026, 12, 1), 1), date(2027, 1, 1))
        self.assertEqual(decaler(date(2026, 10, 1), -14), date(2025, 8, 1))


class CouleurClaireTests(SimpleTestCase):
    def test_melange_a_90_pourcent_de_blanc(self):
        self.assertEqual(couleur_claire("#1B7A2E"), "#E8F2EA")
        self.assertEqual(couleur_claire("#000000"), "#E6E6E6")
        self.assertEqual(couleur_claire("#FFFFFF"), "#FFFFFF")
        self.assertEqual(couleur_claire("1A2B4A", 0.5), "#8D95A5")

    def test_couleur_invalide(self):
        with self.assertRaises(ValueError):
            couleur_claire("#12345")

