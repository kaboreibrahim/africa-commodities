from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from operations.models import Ligne
from operations.selectors import marges_par_mois, synthese_groupe, tableau_de_bord_mois
from repartition.models import RegleRepartition
from societes.models import Client, ObjectifMensuel, Societe


def ligne(societe, **kw):
    data = dict(date=date(2026, 10, 2), reference="MSCU1", quantite=1, marge_unitaire=100_000)
    data.update(kw)
    return Ligne.objects.create(societe=societe, **data)


class LigneCalculTests(TestCase):
    def setUp(self):
        self.ooa = Societe.objects.get(code="ooa")

    def test_repartition_calculee_et_figee(self):
        l = ligne(self.ooa, quantite=10)
        self.assertEqual(l.marge_totale, 1_000_000)
        self.assertEqual(l.part_charges, 250_000)
        self.assertEqual(l.part_africa_commodities, 450_000)
        self.assertEqual((l.part_risques, l.part_provision, l.part_comptes), (100_000, 100_000, 100_000))
        self.assertEqual(l.regle.date_debut, date(2026, 1, 1))

    def test_nouvelle_regle_ne_modifie_pas_l_historique(self):
        ancienne = ligne(self.ooa, date=date(2026, 10, 2))
        RegleRepartition.objects.create(date_debut=date(2027, 1, 1), pct_charges=Decimal("30"),
                                        pct_africa_commodities=Decimal("50"))
        nouvelle = ligne(self.ooa, date=date(2027, 1, 5))
        ancienne.refresh_from_db()
        ancienne.observation = "correction d'un libellé"
        ancienne.save()
        self.assertEqual(ancienne.part_charges, 25_000)   # règle 2026 conservée
        self.assertEqual(nouvelle.part_charges, 30_000)   # règle 2027 appliquée
        self.assertEqual(nouvelle.part_africa_commodities, 35_000)

    def test_modifier_la_quantite_recalcule(self):
        l = ligne(self.ooa)
        l.quantite = 3
        l.save()
        l.refresh_from_db()
        self.assertEqual(l.marge_totale, 300_000)
        self.assertEqual(l.part_africa_commodities, 135_000)

    def test_quantite_nulle_refusee_par_la_base(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ligne(self.ooa, quantite=0)

    def test_client_d_une_autre_societe_refuse(self):
        client_anl = Client.objects.create(societe=Societe.objects.get(code="anl"), nom="CMA CGM")
        l = Ligne(societe=self.ooa, client=client_anl, date=date(2026, 10, 2), reference="X", quantite=1, marge_unitaire=1)
        with self.assertRaises(ValidationError) as e:
            l.full_clean()
        self.assertIn("client", e.exception.message_dict)

    def test_champ_specifique_controle(self):
        alon = Societe.objects.get(code="alon")
        l = Ligne(societe=alon, extra="Bail", date=date(2026, 10, 2), reference="Villa", quantite=1, marge_unitaire=1)
        with self.assertRaises(ValidationError):
            l.full_clean()
        l.extra = "Vente"
        l.full_clean(exclude=["regle", "marge_totale", "part_charges", "part_africa_commodities",
                              "part_risques", "part_provision", "part_comptes"])

    def test_date_sans_regle_refusee(self):
        l = Ligne(societe=self.ooa, date=date(2025, 6, 1), reference="X", quantite=1, marge_unitaire=1)
        with self.assertRaises(ValidationError) as e:
            l.full_clean()
        self.assertIn("date", e.exception.message_dict)

    def test_suppression_douce(self):
        l = ligne(self.ooa)
        l.supprimer()
        self.assertFalse(Ligne.objects.exists())
        self.assertEqual(Ligne.tous.count(), 1)
        l.restaurer()
        self.assertTrue(Ligne.objects.exists())


class SelecteursTests(TestCase):
    def setUp(self):
        self.ooa = Societe.objects.get(code="ooa")
        self.mlp = Societe.objects.get(code="mlp")
        ligne(self.ooa, quantite=15)                                   # 1 500 000
        ligne(self.ooa, quantite=10, marge_unitaire=120_000)           # 1 200 000
        ligne(self.ooa, date=date(2026, 9, 12), quantite=20, marge_unitaire=90_000)  # septembre
        ligne(self.mlp, quantite=250, marge_unitaire=1000, extra="Cocody")           # 250 000
        supprimee = ligne(self.ooa, quantite=99)
        supprimee.supprimer()                                          # ignorée partout

    def test_tableau_de_bord_mois(self):
        ObjectifMensuel.objects.create(societe=self.ooa, mois=date(2026, 10, 1), montant=2_000_000)
        with self.assertNumQueries(2):
            t = tableau_de_bord_mois(self.ooa, date(2026, 10, 7))
        self.assertEqual(t["marge"], 2_700_000)
        self.assertEqual(t["quantite"], 25)
        self.assertEqual(t["africa_commodities"], 1_215_000)
        self.assertEqual(t["objectif"], 2_000_000)
        self.assertTrue(t["objectif_atteint"])

    def test_marges_par_mois(self):
        m = marges_par_mois(self.ooa, 2026)
        self.assertEqual(m[date(2026, 9, 1)], 1_800_000)
        self.assertEqual(m[date(2026, 10, 1)], 2_700_000)
        self.assertEqual(marges_par_mois(None, 2026)[date(2026, 10, 1)], 2_950_000)

    def test_synthese_groupe(self):
        s = {r["societe"].code: r for r in synthese_groupe(date(2026, 10, 1))}
        self.assertEqual(len(s), 5)
        self.assertEqual(s["ooa"]["marge"], 2_700_000)
        self.assertTrue(s["ooa"]["objectif_atteint"])
        self.assertEqual(s["mlp"]["marge"], 250_000)
        self.assertEqual(s["mlp"]["progression"], 25)
        self.assertEqual(s["anl"]["marge"], 0)
        self.assertFalse(s["anl"]["objectif_atteint"])
        self.assertEqual(sum(r["africa_commodities"] for r in s.values()), 1_215_000 + 112_500)
