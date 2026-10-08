from dataclasses import dataclass
from decimal import Decimal

from django.test import SimpleTestCase

from repartition.services import calculer_repartition


@dataclass
class Regle:  # règle « en mémoire » : pas besoin de base de données
    pct_charges: Decimal = Decimal("25")
    pct_africa_commodities: Decimal = Decimal("60")
    parts_risques: int = 1
    parts_provision: int = 1
    parts_comptes: int = 1


class CalculRepartitionTests(SimpleTestCase):
    def test_exemple_flexitanks_5_millions(self):
        r = calculer_repartition(5_000_000, Regle())
        self.assertEqual(r.charges, 1_250_000)
        self.assertEqual(r.africa_commodities, 2_250_000)
        self.assertEqual((r.risques, r.provision, r.comptes), (500_000, 500_000, 500_000))

    def test_un_conteneur_100_000(self):
        r = calculer_repartition(100_000, Regle())
        self.assertEqual((r.charges, r.africa_commodities, r.risques, r.provision, r.comptes),
                         (25_000, 45_000, 10_000, 10_000, 10_000))

    def test_somme_toujours_egale_a_la_marge(self):
        for marge in [1, 7, 333, 1001, 99_999, 123_457, 4_800_001]:
            with self.subTest(marge=marge):
                r = calculer_repartition(marge, Regle())
                self.assertEqual(r.total, marge)

    def test_ecart_arrondi_affecte_aux_comptes(self):
        # 1 001 F : charges 250,25 → 250 ; AC 450,45 → 450 ; solde 300,3 → 100 + 100 + 101
        r = calculer_repartition(1001, Regle())
        self.assertEqual((r.charges, r.africa_commodities, r.risques, r.provision, r.comptes), (250, 450, 100, 100, 101))

    def test_ecart_va_au_dernier_poste_avec_parts(self):
        r = calculer_repartition(1001, Regle(parts_comptes=0))
        self.assertEqual(r.comptes, 0)
        self.assertEqual(r.total, 1001)

    def test_regle_personnalisee(self):
        r = calculer_repartition(1_000_000, Regle(pct_charges=Decimal("20"), pct_africa_commodities=Decimal("50"),
                                                   parts_risques=2, parts_provision=1, parts_comptes=1))
        self.assertEqual((r.charges, r.africa_commodities, r.risques, r.provision, r.comptes),
                         (200_000, 400_000, 200_000, 100_000, 100_000))

    def test_marge_nulle(self):
        self.assertEqual(calculer_repartition(0, Regle()).total, 0)

    def test_marge_negative_refusee(self):
        with self.assertRaises(ValueError):
            calculer_repartition(-1, Regle())

    def test_regle_sans_parts_refusee(self):
        with self.assertRaises(ValueError):
            calculer_repartition(1000, Regle(parts_risques=0, parts_provision=0, parts_comptes=0))
