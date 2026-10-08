"""
Calcul de la répartition de la marge.

C'est le SEUL endroit du projet où la règle est appliquée : les modèles, les vues,
les imports et les tests passent tous par `calculer_repartition`.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

FCFA = Decimal("1")  # le franc CFA n'a pas de centimes : on arrondit à l'unité
CENT = Decimal("100")


def arrondi_fcfa(montant: Decimal) -> Decimal:
    return montant.quantize(FCFA, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Repartition:
    marge: Decimal
    charges: Decimal
    africa_commodities: Decimal
    risques: Decimal
    provision: Decimal
    comptes: Decimal

    @property
    def total(self) -> Decimal:
        return self.charges + self.africa_commodities + self.risques + self.provision + self.comptes

    def as_dict(self) -> dict:
        return {
            "charges": self.charges,
            "africa_commodities": self.africa_commodities,
            "risques": self.risques,
            "provision": self.provision,
            "comptes": self.comptes,
        }


def calculer_repartition(marge, regle) -> Repartition:
    """
    Répartit `marge` (FCFA) selon `regle` (RegleRepartition ou objet équivalent).

    Chaque part est arrondie au franc. L'écart d'arrondi éventuel (quelques francs au plus)
    est affecté à « Comptes », pour que la somme des parts soit TOUJOURS égale à la marge.
    """
    marge = Decimal(marge)
    if marge < 0:
        raise ValueError("La marge ne peut pas être négative.")
    total_parts = regle.parts_risques + regle.parts_provision + regle.parts_comptes
    if total_parts <= 0:
        raise ValueError("La règle doit comporter au moins une part (risques, provision ou comptes).")

    charges_exactes = marge * Decimal(regle.pct_charges) / CENT
    reste = marge - charges_exactes
    ac_exactes = reste * Decimal(regle.pct_africa_commodities) / CENT
    solde = reste - ac_exactes

    charges = arrondi_fcfa(charges_exactes)
    ac = arrondi_fcfa(ac_exactes)
    parts = {
        "risques": arrondi_fcfa(solde * regle.parts_risques / total_parts),
        "provision": arrondi_fcfa(solde * regle.parts_provision / total_parts),
        "comptes": arrondi_fcfa(solde * regle.parts_comptes / total_parts),
    }
    # L'écart d'arrondi va à « Comptes » (ou au dernier poste qui a des parts).
    ecart = marge - charges - ac - sum(parts.values())
    if ecart:
        poste = next(p for p, n in (("comptes", regle.parts_comptes), ("provision", regle.parts_provision),
                                    ("risques", regle.parts_risques)) if n > 0)
        parts[poste] += ecart

    return Repartition(marge=marge, charges=charges, africa_commodities=ac, **parts)
