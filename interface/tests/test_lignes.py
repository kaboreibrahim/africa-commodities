import json

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comptes.tests.jeu import creer_ligne, mois_decale
from operations.models import Ligne
from societes.models import Client, ObjectifMensuel

from .outils import HTMX, JeuInterfaceMixin, compter_requetes

LISTE = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TARGET": "liste-lignes"}


def donnees_ligne(**kw):
    return {"date": timezone.localdate().isoformat(), "reference": "MSCU123", "projet": "PRJ-1", "client": "",
            "quantite": "2", "marge_unitaire": "100000", "observation": "", **kw}


class ApercuTests(JeuInterfaceMixin, TestCase):
    def test_repartition_calculee_par_le_serveur(self):
        self.connecter(self.saisie_ooa)
        reponse = self.client.get(reverse("interface:apercu", args=["ooa"]) + "?quantite=10&marge_unitaire=100000", **HTMX)
        self.assertEqual(reponse.status_code, 200)
        r = reponse.context["repartition"]
        self.assertEqual((r.marge, r.charges, r.africa_commodities, r.risques, r.provision, r.comptes),
                         (1_000_000, 250_000, 450_000, 100_000, 100_000, 100_000))
        for montant in ("250 000 F", "450 000 F", "100 000 F"):
            self.assertContains(reponse, montant)
        self.assertNotContains(reponse, "<html")

    def test_valeurs_invalides(self):
        self.connecter(self.saisie_ooa)
        url = reverse("interface:apercu", args=["ooa"])
        for requete in ("?quantite=abc&marge_unitaire=1", "?quantite=0&marge_unitaire=1", "?quantite=1", ""):
            with self.subTest(requete=requete):
                reponse = self.client.get(url + requete, **HTMX)
                self.assertEqual(reponse.status_code, 200)
                self.assertIsNone(reponse.context["repartition"])


class FormulaireTests(JeuInterfaceMixin, TestCase):
    def page(self, code, user=None):
        self.connecter(user or self.admin_groupe)
        return self.client.get(reverse("interface:lignes", args=[code]))

    def test_libelles_selon_la_societe(self):
        form = self.page("mlp").context["form"]
        self.assertEqual(form.fields["reference"].label, "N° bon / course")
        self.assertEqual(form.fields["quantite"].label, "Nb de livraisons")
        self.assertEqual(form.fields["marge_unitaire"].label, "Marge par livraison (FCFA)")
        self.assertEqual(form["marge_unitaire"].value(), 1000)  # marge par défaut de la société

    def test_champ_specifique(self):
        alon = self.page("alon").context["form"]
        self.assertEqual([c for c, _ in alon.fields["extra"].choices], ["Location", "Vente"])
        mlp = self.page("mlp").context["form"]
        self.assertEqual(mlp.fields["extra"].label, "Zone")
        self.assertNotIn("extra", self.page("ooa").context["form"].fields)
        self.assertNotContains(self.page("ooa"), "<th scope=\"col\">Type</th>")

    def test_clients_de_la_societe_seulement(self):
        Client.objects.create(societe=self.ooa, nom="PALMCI")
        cma = Client.objects.create(societe=self.anl, nom="CMA CGM")
        retire = Client.objects.create(societe=self.ooa, nom="ANCIEN")
        retire.supprimer()
        choix = [nom for _, nom in self.page("ooa").context["form"].fields["client"].choices]
        self.assertEqual(choix, ["— Choisir un client —", "PALMCI"])
        # Un client d'une autre société est refusé
        reponse = self.client.post(reverse("interface:lignes", args=["ooa"]), donnees_ligne(client=cma.pk), **HTMX)
        self.assertEqual(reponse.status_code, 422)
        self.assertFalse(Ligne.objects.filter(reference="MSCU123").exists())


class AjoutTests(JeuInterfaceMixin, TestCase):
    def url(self, code="ooa"):
        return reverse("interface:lignes", args=[code])

    def test_ajout_htmx(self):
        client = Client.objects.create(societe=self.ooa, nom="PALMCI")
        self.connecter(self.saisie_ooa)
        reponse = self.client.post(self.url(), donnees_ligne(client=client.pk, marge_unitaire="120000"), **HTMX)
        self.assertEqual(reponse.status_code, 200)
        self.assertNotContains(reponse, "<html")
        ligne = Ligne.objects.get(reference="MSCU123")
        self.assertEqual((ligne.cree_par, ligne.marge_totale, ligne.client), (self.saisie_ooa, 240_000, client))
        evenements = json.loads(reponse["HX-Trigger"])
        self.assertIn("lignesModifiees", evenements)
        self.assertEqual(evenements["toast"]["message"], "Dossier ajouté(e)")
        # Le formulaire est vidé mais garde date, client et marge
        form = reponse.context["form"]
        self.assertEqual((form["reference"].value(), form["client"].value(), form["marge_unitaire"].value()),
                         (None, client.pk, 120_000))

    def test_erreur_422(self):
        self.connecter(self.saisie_ooa)
        reponse = self.client.post(self.url(), donnees_ligne(quantite="0", reference=""), **HTMX)
        self.assertEqual(reponse.status_code, 422)
        self.assertIn("quantite", reponse.context["form"].errors)
        self.assertIn("reference", reponse.context["form"].errors)
        reponse = self.client.post(self.url(), donnees_ligne(date="1990-01-01"), **HTMX)
        self.assertEqual(reponse.status_code, 422)
        self.assertIn("date", reponse.context["form"].errors)  # erreur du modèle (aucune règle), sous le champ

    def test_sans_javascript(self):
        self.connecter(self.saisie_ooa)
        reponse = self.client.post(self.url(), donnees_ligne())
        self.assertRedirects(reponse, self.url(), fetch_redirect_response=False)
        self.assertTrue(Ligne.objects.filter(reference="MSCU123").exists())
        reponse = self.client.post(self.url(), donnees_ligne(quantite="-1"))
        self.assertEqual(reponse.status_code, 422)
        self.assertContains(reponse, "<html", status_code=422)

    def test_alon_et_mlp(self):
        self.connecter(self.admin_groupe)
        self.client.post(self.url("alon"), donnees_ligne(extra="Vente", reference="Villa B12"), **HTMX)
        self.assertEqual(Ligne.objects.get(reference="Villa B12").extra, "Vente")
        reponse = self.client.post(self.url("alon"), donnees_ligne(extra="Bail", reference="X"), **HTMX)
        self.assertEqual(reponse.status_code, 422)
        self.client.post(self.url("mlp"), donnees_ligne(extra="Cocody", reference="BC-1", marge_unitaire="1000"), **HTMX)
        self.assertEqual(Ligne.objects.get(reference="BC-1").extra, "Cocody")

    def test_droits(self):
        for user, statut in ((self.lecture_ooa, 403), (self.direction, 403), (self.saisie_anl, 404)):
            with self.subTest(user=user.username):
                self.connecter(user)
                with self.assertLogs("securite", "WARNING"):
                    self.assertEqual(self.client.post(self.url(), donnees_ligne()).status_code, statut)
        self.assertFalse(Ligne.objects.filter(reference="MSCU123").exists())

    def test_formulaire_absent_pour_lecture_et_direction(self):
        for user in (self.lecture_ooa, self.direction):
            with self.subTest(user=user.username):
                self.connecter(user)
                reponse = self.client.get(self.url())
                self.assertIsNone(reponse.context["form"])
                self.assertNotContains(reponse, 'id="form-ligne"')


class ConfettisTests(JeuInterfaceMixin, TestCase):
    """Le jeu commun a déjà 200 000 F de marge OOA ce mois-ci."""

    def test_franchissement_une_seule_fois(self):
        ObjectifMensuel.objects.create(societe=self.ooa, mois=mois_decale(0), montant=350_000)
        self.connecter(self.saisie_ooa)
        url = reverse("interface:lignes", args=["ooa"])
        evenements = json.loads(self.client.post(url, donnees_ligne(), **HTMX)["HX-Trigger"])  # 400 000 F
        self.assertEqual(evenements["objectifAtteint"]["societe"], "OOA")
        self.assertEqual(evenements["objectifAtteint"]["couleurs"], ["#1B7A2E", "#E8720C"])
        evenements = json.loads(self.client.post(url, donnees_ligne(reference="B"), **HTMX)["HX-Trigger"])
        self.assertNotIn("objectifAtteint", evenements)

    def test_supprimer_puis_rajouter_relance(self):
        ObjectifMensuel.objects.create(societe=self.ooa, mois=mois_decale(0), montant=350_000)
        self.connecter(self.responsable_ooa)
        url = reverse("interface:lignes", args=["ooa"])
        self.assertIn("objectifAtteint", json.loads(self.client.post(url, donnees_ligne(), **HTMX)["HX-Trigger"]))
        ligne = Ligne.objects.get(reference="MSCU123")
        self.client.post(reverse("interface:ligne_supprimer", args=["ooa", ligne.pk]), **HTMX)
        self.assertIn("objectifAtteint",
                      json.loads(self.client.post(url, donnees_ligne(reference="C"), **HTMX)["HX-Trigger"]))

    def test_modifier_une_observation_ne_relance_pas(self):
        ObjectifMensuel.objects.create(societe=self.ooa, mois=mois_decale(0), montant=150_000)  # déjà atteint
        self.connecter(self.saisie_ooa)
        url = reverse("interface:ligne_modifier", args=["ooa", self.ligne_saisie_ooa.pk])
        reponse = self.client.post(url, donnees_ligne(reference="SAISIE-OOA", quantite="1", observation="ok"), **HTMX)
        self.assertEqual(reponse.status_code, 204)
        self.assertNotIn("objectifAtteint", json.loads(reponse["HX-Trigger"]))

    def test_sans_javascript_message_objectif(self):
        ObjectifMensuel.objects.create(societe=self.ooa, mois=mois_decale(0), montant=350_000)
        self.connecter(self.saisie_ooa)
        reponse = self.client.post(reverse("interface:lignes", args=["ooa"]), donnees_ligne(), follow=True)
        self.assertContains(reponse, 'data-etiquettes="objectif"')
        self.assertContains(reponse, "🎉 Objectif OOA d")


class ListeTests(JeuInterfaceMixin, TestCase):
    def url(self):
        return reverse("interface:lignes", args=["ooa"])

    def test_boutons_selon_les_droits(self):
        self.connecter(self.saisie_ooa)
        reponse = self.client.get(self.url())
        lignes = {l.reference: l for l in reponse.context["page"]}
        self.assertTrue(lignes["SAISIE-OOA"].peut_modifier)
        self.assertFalse(lignes["COLLEGUE-OOA"].peut_modifier)
        self.assertNotContains(reponse, "Supprimer SAISIE-OOA")
        self.assertContains(reponse, "Modifier SAISIE-OOA")
        self.assertNotContains(reponse, "Modifier COLLEGUE-OOA")
        self.connecter(self.responsable_ooa)
        self.assertContains(self.client.get(self.url()), "Supprimer COLLEGUE-OOA")

    def test_total_et_filtres(self):
        Ligne.objects.filter(pk=self.ligne_collegue.pk).update(projet="PRJ-9", observation="urgent")
        self.connecter(self.lecture_ooa)
        reponse = self.client.get(self.url())
        self.assertEqual(reponse.context["totaux"]["marge"], 200_000)
        self.assertContains(reponse, "TOTAL (2 lignes)")
        reponse = self.client.get(self.url() + "?q=urgent", **LISTE)
        self.assertNotContains(reponse, "<html")
        self.assertEqual([l.reference for l in reponse.context["page"]], ["COLLEGUE-OOA"])
        reponse = self.client.get(self.url() + "?projet=PRJ-9&periode=tout")
        self.assertContains(reponse, "<html")  # sans JavaScript : page complète filtrée
        self.assertEqual([l.reference for l in reponse.context["page"]], ["COLLEGUE-OOA"])
        reponse = self.client.get(self.url() + "?periode=tout")
        self.assertEqual(reponse.context["totaux"]["nb_lignes"], 3)  # + la ligne vieille de 3 mois
        reponse = self.client.get(self.url() + "?client=9999&periode=n-importe-quoi")
        self.assertEqual(reponse.status_code, 200)

    def test_pagination(self):
        for i in range(55):
            creer_ligne(self.ooa, self.saisie_ooa, reference=f"P{i}")
        self.connecter(self.lecture_ooa)
        reponse = self.client.get(self.url())
        self.assertEqual(len(reponse.context["page"].object_list), 50)
        self.assertEqual(reponse.context["totaux"]["nb_lignes"], 57)  # total sur tout le filtre
        self.assertEqual(len(self.client.get(self.url() + "?page=2").context["page"].object_list), 7)

    def test_nombre_de_requetes(self):
        for i in range(10):
            creer_ligne(self.ooa, self.saisie_ooa, reference=f"R{i}", client=Client.objects.create(societe=self.ooa, nom=f"C{i}"))
        for user in (self.saisie_ooa, self.direction, self.responsable_ooa):
            with self.subTest(user=user.username):
                self.connecter(user)
                self.client.get(self.url())
                with compter_requetes() as compte:
                    self.assertEqual(self.client.get(self.url()).status_code, 200)
                self.assertLessEqual(compte["nombre"], 6, "\n".join(compte["requetes"]))


class ModificationSuppressionTests(JeuInterfaceMixin, TestCase):
    def test_modification_dialogue(self):
        self.connecter(self.saisie_ooa)
        url = reverse("interface:ligne_modifier", args=["ooa", self.ligne_saisie_ooa.pk])
        dialogue = self.client.get(url, **HTMX)
        self.assertNotContains(dialogue, "<html")
        self.assertContains(dialogue, 'id="modif_reference"')
        reponse = self.client.post(url, donnees_ligne(reference="SAISIE-OOA", quantite="5"), **HTMX)
        self.assertEqual(reponse.status_code, 204)
        self.assertIn("fermerDialogue", json.loads(reponse["HX-Trigger"]))
        self.ligne_saisie_ooa.refresh_from_db()
        self.assertEqual((self.ligne_saisie_ooa.marge_totale, self.ligne_saisie_ooa.modifie_par),
                         (500_000, self.saisie_ooa))

    def test_modification_refusee(self):
        self.connecter(self.saisie_ooa)
        for ligne in (self.ligne_collegue, self.ligne_ancienne):
            with self.subTest(ligne=ligne.reference), self.assertLogs("securite", "WARNING"):
                url = reverse("interface:ligne_modifier", args=["ooa", ligne.pk])
                self.assertEqual(self.client.post(url, donnees_ligne()).status_code, 403)
        self.connecter(self.saisie_anl)
        with self.assertLogs("securite", "WARNING"):
            url = reverse("interface:ligne_modifier", args=["ooa", self.ligne_saisie_ooa.pk])
            self.assertEqual(self.client.get(url).status_code, 404)
        # Une ligne d'une autre société, demandée sous l'adresse d'OOA : 404
        self.connecter(self.admin_groupe)
        self.assertEqual(self.client.get(reverse("interface:ligne_modifier", args=["ooa", self.ligne_anl.pk])).status_code, 404)

    def test_suppression_avec_annulation(self):
        self.connecter(self.responsable_ooa)
        reponse = self.client.post(reverse("interface:ligne_supprimer", args=["ooa", self.ligne_collegue.pk]), **HTMX)
        self.assertEqual((reponse.status_code, reponse.content), (200, b""))
        action = json.loads(reponse["HX-Trigger"])["toast"]["action"]
        self.assertEqual(action["libelle"], "Annuler")
        self.assertTrue(Ligne.tous.get(pk=self.ligne_collegue.pk).est_supprime)
        self.client.post(action["url"], **HTMX)
        self.assertFalse(Ligne.tous.get(pk=self.ligne_collegue.pk).est_supprime)

    def test_suppression_refusee_a_la_saisie(self):
        self.connecter(self.saisie_ooa)
        with self.assertLogs("securite", "WARNING"):
            url = reverse("interface:ligne_supprimer", args=["ooa", self.ligne_saisie_ooa.pk])
            self.assertEqual(self.client.post(url, **HTMX).status_code, 403)
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_corbeille(self):
        self.ligne_collegue.supprimer()
        self.connecter(self.responsable_ooa)
        reponse = self.client.get(reverse("interface:corbeille", args=["ooa"]))
        self.assertContains(reponse, "Restaurer COLLEGUE-OOA")
        for user in (self.saisie_ooa, self.lecture_ooa):
            with self.subTest(user=user.username):
                self.connecter(user)
                with self.assertLogs("securite", "WARNING"):
                    self.assertEqual(self.client.get(reverse("interface:corbeille", args=["ooa"])).status_code, 403)


