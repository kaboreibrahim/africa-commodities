from datetime import date

from django.test import TestCase
from django.urls import reverse

from comptes.tests.jeu import creer_ligne, mois_decale
from operations.selectors import marges_par_mois, marges_par_mois_par_societe, synthese_groupe, totaux_synthese
from societes.models import DepenseMensuelle, ObjectifMensuel, Societe

from .outils import JeuInterfaceMixin, compter_requetes


class SelecteursGroupeTests(JeuInterfaceMixin, TestCase):
    def test_marges_par_mois_par_societe_une_requete(self):
        creer_ligne(self.anl, self.saisie_anl, date=date(2026, 3, 10), quantite=3)
        with self.assertNumQueries(1):
            par_societe = marges_par_mois_par_societe(2026)
        for societe in Societe.objects.all():  # même résultat que marges_par_mois société par société
            self.assertEqual(par_societe.get(societe.pk, {}), marges_par_mois(societe, 2026))

    def test_synthese_meme_resultat_qu_objectif_pour(self):
        ObjectifMensuel.objects.create(societe=self.ooa, mois=date(2026, 1, 1), montant=2_000_000)
        mois = mois_decale(0)
        for ligne in synthese_groupe(mois):
            self.assertEqual(ligne["objectif"], ligne["societe"].objectif_pour(mois))

    def test_totaux_synthese(self):
        mois = mois_decale(0)
        ObjectifMensuel.objects.create(societe=self.ooa, mois=mois, montant=150_000)
        DepenseMensuelle.objects.create(societe=self.ooa, mois=mois, montant=40_000)   # part 50 000 : couvert
        DepenseMensuelle.objects.create(societe=self.anl, mois=mois, montant=100_000)  # part 25 000 : non couvert
        total = totaux_synthese(synthese_groupe(mois))
        self.assertEqual(total["marge"], 300_000)  # OOA 200 000 + ANL 100 000
        self.assertEqual([s.code for s in total["a_l_objectif"]], ["ooa"])
        self.assertEqual([s.code for s in total["charges_couvertes"]], ["ooa"])
        self.assertEqual((total["charges"], total["depenses"]), (75_000, 140_000))
        self.assertEqual(str(total["taux_couverture"]), "53.6")  # 75 000 ÷ 140 000 (OOA et ANL ont saisi)
        self.assertEqual(total["ecart_charges"], -65_000)
        # Une société sans dépenses saisies ne fausse pas la couverture du groupe
        creer_ligne(Societe.objects.get(code="otl"), self.admin_groupe, quantite=10)
        total = totaux_synthese(synthese_groupe(mois))
        self.assertEqual((total["charges"], total["charges_avec_depenses"], total["nb_depenses_saisies"]),
                         (325_000, 75_000, 2))
        self.assertEqual(str(total["taux_couverture"]), "53.6")


class VueGroupeTests(JeuInterfaceMixin, TestCase):
    url = reverse("interface:groupe")

    def test_acces(self):
        for user in (self.admin_groupe, self.direction):
            with self.subTest(user=user.username):
                self.connecter(user)
                self.assertEqual(self.client.get(self.url).status_code, 200)
        for user in (self.responsable_ooa, self.saisie_ooa, self.lecture_ooa, self.saisie_anl):
            with self.subTest(user=user.username):
                self.connecter(user)
                with self.assertLogs("securite", "WARNING"):
                    self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_contenu(self):
        mois = mois_decale(0)
        DepenseMensuelle.objects.create(societe=self.ooa, mois=mois, montant=40_000)
        self.connecter(self.direction)
        reponse = self.client.get(self.url)
        for texte in ("Marge du groupe", "Sociétés à l'objectif", "Sociétés aux charges couvertes", "1 / 5",
                      "Total Africa Commodities", "TOTAL GROUPE", "Reste / Excédent", "non saisies",
                      'data-href="/s/ooa/"', 'data-graphique="groupe-charges"', 'data-graphique="groupe-mois"'):
            self.assertContains(reponse, texte)
        self.assertNotContains(reponse, 'id="form-ligne"')  # aucun formulaire de saisie
        donnees = reponse.context["graphiques"]
        self.assertEqual(len(donnees["mois"]["series"]), 5)
        self.assertEqual(len(donnees["mois"]["tableau"]), 12)
        self.assertEqual(donnees["charges"]["etiquettes"][0], "OOA ✔")
        self.assertAlmostEqual(sum(p["part"] for p in donnees["africaCommodities"]["parts"]), 100.0)

    def test_nombre_de_requetes(self):
        for code in ("anl", "otl", "alon", "mlp"):
            creer_ligne(Societe.objects.get(code=code), self.admin_groupe)
        for user in (self.direction, self.admin_groupe):
            with self.subTest(user=user.username):
                self.connecter(user)
                self.client.get(self.url)
                with compter_requetes() as compte:
                    self.assertEqual(self.client.get(self.url).status_code, 200)
                self.assertLessEqual(compte["nombre"], 12, "\n".join(compte["requetes"]))
