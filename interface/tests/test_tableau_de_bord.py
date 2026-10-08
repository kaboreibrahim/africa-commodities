import json
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from comptes.tests.jeu import creer_ligne, mois_decale
from operations.selectors import (objectifs_resolus, regrouper_projets, tableau_de_bord_societe,
                                  unites_restantes)
from societes.models import ObjectifMensuel

from .outils import HTMX, JeuInterfaceMixin, compter_requetes


class SelecteursTableauDeBordTests(JeuInterfaceMixin, TestCase):
    def test_objectifs_resolus_une_seule_requete(self):
        ObjectifMensuel.objects.create(societe=self.ooa, mois=date(2026, 3, 1), montant=2_000_000)
        ObjectifMensuel.objects.create(societe=self.ooa, mois=date(2026, 6, 1), montant=3_000_000)
        mois = [date(2026, m, 1) for m in range(1, 13)]
        with self.assertNumQueries(1):
            resolus = objectifs_resolus([self.ooa, self.anl], mois)
        for m in mois:  # même résultat que la méthode du modèle
            self.assertEqual(resolus[(self.ooa.pk, m)], self.ooa.objectif_pour(m))
            self.assertEqual(resolus[(self.anl.pk, m)], self.anl.objectif_pour(m))
        self.assertEqual(resolus[(self.ooa.pk, date(2026, 2, 1))], 1_000_000)
        self.assertEqual(resolus[(self.ooa.pk, date(2026, 5, 1))], 2_000_000)
        self.assertEqual(resolus[(self.ooa.pk, date(2026, 12, 1))], 3_000_000)

    def test_unites_restantes(self):
        self.assertEqual(unites_restantes(Decimal(300_000), Decimal(1_000_000), 3, 100_000), 7)
        self.assertEqual(unites_restantes(Decimal(250_000), Decimal(1_000_000), 2, 100_000), 6)  # 125 000 / unité
        self.assertEqual(unites_restantes(Decimal(0), Decimal(1_000_000), 0, 100_000), 10)
        self.assertEqual(unites_restantes(Decimal(1_200_000), Decimal(1_000_000), 12, 100_000), 0)
        self.assertEqual(unites_restantes(Decimal(0), Decimal(0), 0, 100_000), 0)

    def test_regrouper_projets(self):
        projets = [{"projet": f"P{i}", "marge": Decimal(100 - i), "quantite": 1} for i in range(10)]
        regroupes = regrouper_projets(projets)
        self.assertEqual(len(regroupes), 8)
        self.assertEqual(regroupes[-1], {"projet": "Autres projets", "marge": Decimal(93 + 92 + 91), "quantite": 3})
        self.assertEqual(len(regrouper_projets(projets[:8])), 8)  # 8 projets : pas de regroupement
        self.assertEqual(regrouper_projets([{"projet": "", "marge": 1, "quantite": 1}])[0]["projet"], "(sans projet)")

    def test_tableau_de_bord_societe(self):
        mois = mois_decale(0)
        donnees = tableau_de_bord_societe(self.ooa, mois)
        ind = donnees["indicateurs"]
        self.assertEqual(ind["marge"], 200_000)  # lignes SAISIE-OOA et COLLEGUE-OOA
        self.assertEqual(ind["quantite"], 2)
        self.assertEqual(ind["marge_moyenne"], 100_000)
        self.assertEqual(ind["unites_restantes"], 8)
        self.assertEqual(ind["pct_charges"], 25)
        self.assertEqual(ind["pct_africa_commodities"], 60)
        self.assertEqual(ind["risques_et_provision"], 40_000)
        self.assertEqual(len(donnees["annee"]), 12)
        self.assertTrue(donnees["annee"][mois.month - 1]["selectionne"])
        self.assertEqual(donnees["projets"], [{"projet": "(sans projet)", "marge": 200_000, "quantite": 2}])


class TableauDeBordVueTests(JeuInterfaceMixin, TestCase):
    def url(self, code="ooa"):
        return reverse("interface:tableau", args=[code])

    def test_contenu(self):
        self.connecter(self.lecture_ooa)
        reponse = self.client.get(self.url())
        self.assertEqual(reponse.status_code, 200)
        for texte in ("Marge d", "Conteneurs du mois", "Couverture des charges (25", "Africa Commodities", "Risques + Provision",
                      "Comptes OOA (disponible)", "Voir les données", "≈ 8 conteneur(s) restant(s)"):
            self.assertContains(reponse, texte)
        donnees = json.loads(reponse.context["graphiques"] and json.dumps(reponse.context["graphiques"]))
        self.assertEqual([p["valeur"] for p in donnees["repartition"]["parts"]], [50000, 90000, 20000, 20000, 20000])
        self.assertEqual(len(donnees["mois"]["marges"]), 12)
        self.assertContains(reponse, 'id="donnees-graphiques" type="application/json"')

    def test_libelles_selon_la_societe(self):
        self.connecter(self.direction)
        self.assertContains(self.client.get(self.url("mlp")), "Livraisons du mois")
        self.assertContains(self.client.get(self.url("alon")), "Opérations du mois")

    def test_bandeau_objectif_atteint(self):
        ObjectifMensuel.objects.create(societe=self.ooa, mois=mois_decale(0), montant=150_000)
        self.connecter(self.lecture_ooa)
        reponse = self.client.get(self.url())
        self.assertContains(reponse, "atteint : 200 000 F pour un objectif de 150 000 F")
        self.assertContains(reponse, "✔ Objectif atteint")

    def test_graphique_vide(self):
        self.connecter(self.direction)
        reponse = self.client.get(self.url("otl"))
        self.assertContains(reponse, "Aucune donnée sur la période")

    def test_bouton_objectif_selon_le_role(self):
        for user, visible in ((self.responsable_ooa, True), (self.admin_groupe, True), (self.saisie_ooa, False),
                              (self.lecture_ooa, False), (self.direction, False)):
            with self.subTest(user=user.username):
                self.connecter(user)
                reponse = self.client.get(self.url())
                (self.assertContains if visible else self.assertNotContains)(reponse, "Modifier l'objectif")

    def test_fragment_htmx(self):
        self.connecter(self.lecture_ooa)
        reponse = self.client.get(self.url(), **HTMX)
        self.assertNotContains(reponse, "<html")
        self.assertContains(reponse, 'id="tableau-de-bord"')
        self.assertContains(self.client.get(self.url()), "<html")

    def test_nombre_de_requetes(self):
        for _ in range(3):
            creer_ligne(self.ooa, self.saisie_ooa, projet="PRJ-1", date=mois_decale(1))
        for user, maximum in ((self.saisie_ooa, 8), (self.direction, 8), (self.responsable_ooa, 8)):
            with self.subTest(user=user.username):
                self.connecter(user)
                self.client.get(self.url())  # cache de la règle en vigueur
                with compter_requetes() as compte:
                    self.assertEqual(self.client.get(self.url()).status_code, 200)
                self.assertLessEqual(compte["nombre"], maximum, "\n".join(compte["requetes"]))


class ObjectifVueTests(JeuInterfaceMixin, TestCase):
    def url(self):
        return reverse("interface:objectif", args=["ooa"])

    def test_definir_en_htmx(self):
        self.connecter(self.responsable_ooa)
        formulaire = self.client.get(self.url(), **HTMX)
        self.assertContains(formulaire, "celui du dernier mois renseigné")
        self.assertContains(formulaire, 'value="1000000"')  # valeur non localisée dans un champ numérique
        self.assertNotContains(formulaire, "<html")
        reponse = self.client.post(self.url(), {"montant": "2500000"}, **HTMX)
        self.assertEqual(reponse.status_code, 204)
        evenements = json.loads(reponse["HX-Trigger"])
        self.assertIn("objectifModifie", evenements)
        self.assertIn("Objectif d", evenements["toast"]["message"])
        objectif = ObjectifMensuel.objects.get()
        self.assertEqual((objectif.mois, objectif.montant), (mois_decale(0), 2_500_000))
        self.assertEqual(objectif.history.first().history_user, self.responsable_ooa)

    def test_sans_javascript(self):
        self.connecter(self.admin_groupe)
        self.assertContains(self.client.get(self.url()), "<html")
        reponse = self.client.post(self.url(), {"montant": "900000"})
        self.assertRedirects(reponse, reverse("interface:tableau", args=["ooa"]), fetch_redirect_response=False)

    def test_montant_invalide_422(self):
        self.connecter(self.responsable_ooa)
        reponse = self.client.post(self.url(), {"montant": "-5"}, **HTMX)
        self.assertEqual(reponse.status_code, 422)
        self.assertFalse(ObjectifMensuel.objects.exists())

    def test_refuse_aux_autres_roles(self):
        for user, statut in ((self.saisie_ooa, 403), (self.lecture_ooa, 403), (self.direction, 403),
                             (self.saisie_anl, 404)):
            with self.subTest(user=user.username):
                self.connecter(user)
                with self.assertLogs("securite", "WARNING"):
                    self.assertEqual(self.client.post(self.url(), {"montant": "1"}).status_code, statut)
        self.assertFalse(ObjectifMensuel.objects.exists())
