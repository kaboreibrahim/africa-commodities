from datetime import date
from decimal import Decimal

from django.test import TestCase

from operations.models import Ligne
from operations.selectors import (charges_vs_depenses_par_mois, couverture_charges, synthese_groupe,
                                  tableau_de_bord_mois, tableau_de_bord_societe, unites_restantes)
from repartition.models import RegleRepartition
from societes.models import DepenseMensuelle, Societe

OCTOBRE = date(2026, 10, 1)


def ligne(societe, quantite, marge_unitaire, jour=date(2026, 10, 5), **kw):
    return Ligne.objects.create(societe=societe, date=jour, reference="R", quantite=quantite,
                                marge_unitaire=marge_unitaire, **kw)


class CouvertureCalculTests(TestCase):
    """Les 3 cas de contrôle du cahier des charges, avec les valeurs exactes."""

    def setUp(self):
        self.ooa = Societe.objects.get(code="ooa")

    def test_pas_couvert(self):
        c = couverture_charges(self.ooa, OCTOBRE, marge=2_000_000, part_charges=500_000, quantite=20,
                               depenses=1_200_000)
        self.assertFalse(c.couvert)
        self.assertTrue(c.depenses_saisies)
        self.assertEqual(c.reste_a_couvrir, 700_000)
        self.assertEqual(c.excedent, 0)
        self.assertEqual(c.taux, Decimal("41.7"))
        self.assertEqual(c.marge_necessaire, 4_800_000)
        self.assertEqual(c.marge_restante, 2_800_000)
        self.assertEqual(c.unites_restantes, 28)  # conteneurs à 100 000 F

    def test_couvert(self):
        c = couverture_charges(self.ooa, OCTOBRE, marge=4_800_000, part_charges=1_200_000, quantite=48,
                               depenses=1_000_000)
        self.assertTrue(c.couvert)
        self.assertEqual(c.excedent, 200_000)
        self.assertEqual(c.reste_a_couvrir, 0)
        self.assertEqual(c.taux, Decimal("120.0"))
        self.assertEqual(c.marge_necessaire, 4_000_000)  # 1 000 000 F ÷ 25 %
        self.assertEqual((c.marge_restante, c.unites_restantes), (0, 0))

    def test_depenses_non_saisies(self):
        c = couverture_charges(self.ooa, OCTOBRE, marge=1_000_000, part_charges=250_000, quantite=10, depenses=0)
        self.assertIsNone(c.taux)
        self.assertFalse(c.depenses_saisies)
        self.assertFalse(c.couvert)
        self.assertEqual((c.marge_necessaire, c.unites_restantes, c.excedent), (0, 0, 0))

    def test_depenses_chargees_si_non_fournies(self):
        DepenseMensuelle.objects.create(societe=self.ooa, mois=OCTOBRE, montant=1_200_000)
        with self.assertNumQueries(2):  # dépenses + règle du mois
            c = couverture_charges(self.ooa, date(2026, 10, 20), marge=2_000_000, part_charges=500_000, quantite=20)
        self.assertEqual(c.marge_necessaire, 4_800_000)

    def test_regle_a_30_pourcent_en_2027(self):
        RegleRepartition.objects.create(date_debut=date(2027, 1, 1), pct_charges=Decimal("30"),
                                        pct_africa_commodities=Decimal("60"))
        c = couverture_charges(self.ooa, date(2027, 3, 1), marge=0, part_charges=0, quantite=0, depenses=1_200_000)
        self.assertEqual(c.marge_necessaire, 4_000_000)  # 1 200 000 F ÷ 30 %
        self.assertEqual(c.unites_restantes, 40)  # pas encore de ligne : marge par défaut 100 000 F

    def test_mon_livreur_pro_marge_par_livraison(self):
        mlp = Societe.objects.get(code="mlp")
        c = couverture_charges(mlp, OCTOBRE, marge=0, part_charges=0, quantite=0, depenses=100_000)
        self.assertEqual(c.marge_necessaire, 400_000)
        self.assertEqual(c.unites_restantes, 400)  # 400 000 F ÷ 1 000 F par livraison
        c = couverture_charges(mlp, OCTOBRE, marge=150_000, part_charges=37_500, quantite=120, depenses=100_000)
        self.assertEqual(c.unites_restantes, 200)  # (400 000 − 150 000) ÷ 1 250 F

    def test_arrondi_au_superieur(self):
        c = couverture_charges(self.ooa, OCTOBRE, marge=150_000, part_charges=37_500, quantite=1, depenses=100_000)
        self.assertEqual(c.marge_restante, 250_000)
        self.assertEqual(c.unites_restantes, 2)  # 250 000 ÷ 150 000 = 1,67 -> 2
        self.assertEqual(unites_restantes(Decimal(150_000), Decimal(400_000), 1, 100_000), 2)


class CouvertureSelecteursTests(TestCase):
    def setUp(self):
        self.ooa = Societe.objects.get(code="ooa")
        ligne(self.ooa, 20, 100_000)                     # 2 000 000 F de marge, 500 000 F de charges
        DepenseMensuelle.objects.create(societe=self.ooa, mois=OCTOBRE, montant=1_200_000)

    def test_tableau_de_bord_mois(self):
        with self.assertNumQueries(4):
            t = tableau_de_bord_mois(self.ooa, OCTOBRE)
        self.assertEqual(t["depenses"], 1_200_000)
        self.assertEqual(t["couverture"].reste_a_couvrir, 700_000)
        self.assertEqual(t["couverture"].unites_restantes, 28)

    def test_pas_de_report_d_un_mois_sur_l_autre(self):
        DepenseMensuelle.objects.create(societe=self.ooa, mois=date(2026, 9, 1), montant=900_000)
        DepenseMensuelle.objects.filter(mois=OCTOBRE).delete()
        t = tableau_de_bord_mois(self.ooa, OCTOBRE)
        self.assertEqual(t["depenses"], 0)
        self.assertIsNone(t["couverture"].taux)
        self.assertEqual(tableau_de_bord_mois(self.ooa, date(2026, 9, 1))["depenses"], 900_000)

    def test_synthese_groupe(self):
        DepenseMensuelle.objects.create(societe=Societe.objects.get(code="mlp"), mois=OCTOBRE, montant=10_000)
        with self.assertNumQueries(5):
            synthese = synthese_groupe(OCTOBRE)
        self.assertEqual(len(synthese), 5)
        par_code = {r["societe"].code: r for r in synthese}
        self.assertEqual(par_code["ooa"]["depenses"], 1_200_000)
        self.assertFalse(par_code["ooa"]["couverture"].couvert)
        self.assertEqual(par_code["anl"]["depenses"], 0)
        self.assertIsNone(par_code["anl"]["couverture"].taux)
        self.assertEqual(par_code["mlp"]["couverture"].reste_a_couvrir, 10_000)
        # Nombre de requêtes stable : il ne dépend pas du nombre de sociétés
        Societe.objects.filter(code="otl").update(actif=False)
        with self.assertNumQueries(5):
            self.assertEqual(len(synthese_groupe(OCTOBRE)), 4)

    def test_charges_vs_depenses_par_mois(self):
        DepenseMensuelle.objects.create(societe=self.ooa, mois=date(2026, 3, 1), montant=50_000)
        with self.assertNumQueries(2):
            annee = charges_vs_depenses_par_mois(self.ooa, 2026)
        self.assertEqual(len(annee), 12)
        self.assertEqual(annee[9], {"mois": OCTOBRE, "part_charges": 500_000, "depenses": 1_200_000})
        self.assertEqual(annee[2]["depenses"], 50_000)
        self.assertEqual(annee[0], {"mois": date(2026, 1, 1), "part_charges": 0, "depenses": 0})

    def test_tableau_de_bord_societe_coherent(self):
        with self.assertNumQueries(5):
            donnees = tableau_de_bord_societe(self.ooa, OCTOBRE)
        ind, reference = donnees["indicateurs"], tableau_de_bord_mois(self.ooa, OCTOBRE)
        for cle in ("marge", "charges", "africa_commodities", "quantite", "objectif", "progression", "depenses",
                    "couverture"):
            self.assertEqual(ind[cle], reference[cle], cle)
        self.assertEqual([(m["part_charges"], m["depenses"]) for m in donnees["annee"]],
                         [(m["part_charges"], m["depenses"]) for m in charges_vs_depenses_par_mois(self.ooa, 2026)])
