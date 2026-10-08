import json

from django.test import TestCase
from django.urls import reverse

from comptes.tests.jeu import creer_ligne, mois_decale
from societes.models import DepenseMensuelle

from .outils import HTMX, JeuInterfaceMixin, compter_requetes


class CarteCouvertureTests(JeuInterfaceMixin, TestCase):
    """Le jeu commun donne à OOA 200 000 F de marge ce mois-ci, donc 50 000 F de part charges."""

    def page(self, user=None):
        self.connecter(user or self.lecture_ooa)
        return self.client.get(reverse("interface:tableau", args=["ooa"]))

    def test_depenses_non_saisies(self):
        reponse = self.page()
        self.assertContains(reponse, "Couverture des charges")
        self.assertContains(reponse, "Dépenses non saisies")
        self.assertNotContains(reponse, "Charges du mois couvertes")

    def test_charges_non_couvertes(self):
        DepenseMensuelle.objects.create(societe=self.ooa, mois=mois_decale(0), montant=120_000)
        reponse = self.page()
        # reste 70 000 F ; marge nécessaire 480 000 F ; reste à faire 280 000 F à 100 000 F -> 3 conteneurs
        self.assertContains(reponse, "⚠</span> Reste à couvrir 70 000 F — ≈ 3 conteneur(s)")
        self.assertContains(reponse, "Taux de couverture : 41,7 %")
        self.assertNotContains(reponse, "Charges du mois couvertes")

    def test_charges_couvertes(self):
        DepenseMensuelle.objects.create(societe=self.ooa, mois=mois_decale(0), montant=40_000)
        reponse = self.page()
        self.assertContains(reponse, "✔</span> Charges couvertes — excédent 10 000 F")
        self.assertContains(reponse, "Taux de couverture : 125 %")
        self.assertContains(reponse, 'value="100"')  # barre plafonnée à 100 %
        self.assertContains(reponse, "Charges du mois couvertes")

    def test_graphique_charges_depenses(self):
        DepenseMensuelle.objects.create(societe=self.ooa, mois=mois_decale(0), montant=40_000)
        reponse = self.page()
        donnees = reponse.context["graphiques"]["chargesDepenses"]
        i = mois_decale(0).month - 1
        self.assertEqual((donnees["parts"][i], donnees["depenses"][i], donnees["ecarts"][i]), (50_000, 40_000, 10_000))
        self.assertContains(reponse, 'data-graphique="charges-depenses"')

    def test_bouton_selon_le_role(self):
        self.assertContains(self.page(self.responsable_ooa), "Saisir les dépenses")
        for user in (self.saisie_ooa, self.lecture_ooa, self.direction):
            with self.subTest(user=user.username):
                self.assertNotContains(self.page(user), "Saisir les dépenses")

    def test_limite_de_requetes_toujours_respectee(self):
        DepenseMensuelle.objects.create(societe=self.ooa, mois=mois_decale(0), montant=40_000)
        self.connecter(self.saisie_ooa)
        url = reverse("interface:tableau", args=["ooa"])
        self.client.get(url)
        with compter_requetes() as compte:
            self.client.get(url)
        self.assertLessEqual(compte["nombre"], 8, "\n".join(compte["requetes"]))


class SaisieDepensesTests(JeuInterfaceMixin, TestCase):
    def url(self, code="ooa"):
        return reverse("interface:depenses", args=[code])

    def test_saisie_htmx_et_franchissement_unique(self):
        self.connecter(self.responsable_ooa)
        formulaire = self.client.get(self.url(), **HTMX)
        self.assertNotContains(formulaire, "<html")
        self.assertContains(formulaire, "pas reporté sur les mois suivants")

        # 80 000 F de dépenses : 50 000 F de part charges ne suffisent pas
        reponse = self.client.post(self.url(), {"montant": "80000", "note": "loyer"}, **HTMX)
        self.assertEqual(reponse.status_code, 204)
        evenements = json.loads(reponse["HX-Trigger"])
        self.assertIn("depensesModifiees", evenements)
        self.assertNotIn("chargesCouvertes", evenements)

        # 45 000 F : les charges deviennent couvertes -> notification (sans confettis)
        evenements = json.loads(self.client.post(self.url(), {"montant": "45000"}, **HTMX)["HX-Trigger"])
        self.assertEqual(evenements["chargesCouvertes"]["societe"], "OOA")
        self.assertNotIn("objectifAtteint", evenements)

        # 40 000 F : toujours couvertes -> pas de nouvelle notification
        evenements = json.loads(self.client.post(self.url(), {"montant": "40000"}, **HTMX)["HX-Trigger"])
        self.assertNotIn("chargesCouvertes", evenements)

        depense = DepenseMensuelle.objects.get()
        self.assertEqual((depense.montant, depense.saisi_par, depense.mois), (40_000, self.responsable_ooa, mois_decale(0)))

    def test_ligne_qui_couvre_les_charges(self):
        """Le franchissement par une nouvelle ligne est détecté par les mêmes outils (cf. lot 3.3)."""
        from operations.selectors import etat_du_mois
        from operations.services import franchissements

        DepenseMensuelle.objects.create(societe=self.ooa, mois=mois_decale(0), montant=60_000)
        avant = etat_du_mois(self.ooa, mois_decale(0))
        creer_ligne(self.ooa, self.saisie_ooa)
        self.assertEqual(franchissements(avant, etat_du_mois(self.ooa, mois_decale(0))), {"charges_couvertes"})

    def test_sans_javascript(self):
        self.connecter(self.admin_groupe)
        self.assertContains(self.client.get(self.url("anl")), "<html")
        reponse = self.client.post(self.url("anl"), {"montant": "300000"})
        self.assertRedirects(reponse, reverse("interface:tableau", args=["anl"]), fetch_redirect_response=False)

    def test_erreur_422(self):
        self.connecter(self.responsable_ooa)
        self.assertEqual(self.client.post(self.url(), {"montant": "-1"}, **HTMX).status_code, 422)
        self.assertFalse(DepenseMensuelle.objects.exists())

    def test_refus(self):
        for user, statut in ((self.saisie_ooa, 403), (self.lecture_ooa, 403), (self.direction, 403),
                             (self.responsable_ooa, 404)):
            with self.subTest(user=user.username):
                self.connecter(user)
                with self.assertLogs("securite", "WARNING"):
                    url = self.url("anl") if user == self.responsable_ooa else self.url()
                    self.assertEqual(self.client.post(url, {"montant": "1"}).status_code, statut)
        self.assertFalse(DepenseMensuelle.objects.exists())
