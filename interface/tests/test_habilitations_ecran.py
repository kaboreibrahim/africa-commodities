"""Écran « Habilitations » (admin groupe), commandes de rapport et d'expiration."""
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comptes import acces, services
from comptes.models import Affectation, HabilitationVueGroupe, JournalSecurite, Utilisateur
from comptes.tests.jeu import ReinitialiserAxesMixin, activer_totp, creer_utilisateur
from interface import habilitations as logique
from societes.models import Societe

from .outils import HTMX, JeuInterfaceMixin
from .test_qualite import AnalyseurCSP

E = JournalSecurite.Evenement


class EcranBase(ReinitialiserAxesMixin, JeuInterfaceMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.cible = creer_utilisateur("cible")
        self.fiche = reverse("interface:habilitation_fiche", args=[self.cible.pk])
        self.connecter(self.admin_groupe)

    def donnees_acces(self, **roles):
        """Corps du formulaire « accès par société » (un rôle par code société, les autres à « Aucun »)."""
        donnees = {"bloc": "acces"}
        for s in Societe.objects.filter(actif=True):
            donnees[f"role_{s.code}"] = roles.get(s.code, "")
        return donnees


class AccesEcranTests(EcranBase):
    def urls(self):
        return [reverse("interface:habilitations"), reverse("interface:habilitations_matrice"),
                reverse("interface:habilitation_nouveau"), self.fiche]

    def test_seul_l_admin_groupe_y_accede(self):
        for url in self.urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        for utilisateur in (self.responsable_ooa, self.saisie_ooa, self.direction, self.lecture_ooa):
            self.connecter(utilisateur)
            for url in self.urls():
                with self.subTest(utilisateur=utilisateur.username, url=url), self.assertLogs("securite", "WARNING"):
                    self.assertEqual(self.client.get(url).status_code, 404)
        self.connecter(self.saisie_ooa)
        with self.assertLogs("securite", "WARNING"):
            self.assertEqual(self.client.post(self.fiche, {"bloc": "activer"}).status_code, 404)

    def test_anonyme_redirige_vers_la_connexion(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("interface:habilitations")).status_code, 302)

    def test_lien_dans_le_menu_reserve_a_l_admin(self):
        reponse = self.client.get(reverse("interface:habilitations"))
        self.assertContains(reponse, f'href="{reverse("interface:habilitations")}"')
        self.connecter(self.responsable_ooa)
        self.assertNotContains(self.client.get("/s/ooa/"), "/administration/habilitations/")

    def test_csp_des_nouvelles_pages(self):
        services.accorder_vue_groupe(self.admin_groupe, self.cible, portee="toutes", motif="Test")
        for url in self.urls():
            with self.subTest(url=url):
                analyseur = AnalyseurCSP()
                analyseur.feed(self.client.get(url).content.decode())
                self.assertEqual(analyseur.problemes, [])


class ListeTests(EcranBase):
    def test_colonnes_badges_et_filtres(self):
        hier = timezone.localdate() - timedelta(days=1)
        dans_10 = timezone.localdate() + timedelta(days=10)
        services.accorder_acces_societe(self.admin_groupe, self.cible, self.ooa, "responsable", date_fin=dans_10)
        services.accorder_acces_societe(self.admin_groupe, self.cible, self.anl, "saisie", date_fin=hier)
        services.accorder_vue_groupe(self.admin_groupe, self.cible, portee="selection", societes=[self.ooa, self.anl],
                                     detail_autorise=True, motif="Test")
        url = reverse("interface:habilitations")
        reponse = self.client.get(url, {"q": "cible"})
        self.assertContains(reponse, "OOA · Responsable")
        self.assertContains(reponse, f"jusqu'au {dans_10:%d/%m/%Y}")
        self.assertContains(reponse, "badge-acces--expiree")  # accès expiré : badge barré
        self.assertContains(reponse, "OOA, ANL")  # portée de la Vue Groupe
        self.assertContains(reponse, "(détail autorisé)")
        self.assertEqual(len(reponse.context["lignes"]), 1)

        def noms(**filtres):
            return {l["u"].username for l in self.client.get(url, filtres).context["lignes"]}

        self.assertIn("cible", noms(vue_groupe="oui"))
        self.assertNotIn("cible", noms(vue_groupe="non"))
        self.assertIn("direction", noms(vue_groupe="oui"))
        self.assertIn("cible", noms(expire_bientot="on"))
        self.assertNotIn("cible", noms(actif="non"))
        self.assertIn("cible", noms(mfa_manquante="on"))
        self.assertIn("cible", noms(societe="anl"))
        self.assertNotIn("saisie_anl", noms(societe="ooa"))

    def test_fragment_htmx(self):
        reponse = self.client.get(reverse("interface:habilitations"), {"q": "direction"}, HTTP_HX_REQUEST="true")
        self.assertContains(reponse, 'id="liste-utilisateurs"')
        self.assertNotContains(reponse, "<html")


class FicheTests(EcranBase):
    def test_accorder_un_acces_en_deux_etapes(self):
        reponse = self.client.post(self.fiche, self.donnees_acces(mlp="saisie"))
        self.assertContains(reponse, "donner Saisie sur MLP")
        self.assertFalse(Affectation.objects.filter(utilisateur=self.cible).exists())  # rien avant confirmation
        champs = {"bloc": "acces", "etape": "confirmer", "motif": "Remplacement", **self.donnees_acces(mlp="saisie")}
        reponse = self.client.post(self.fiche, champs)
        self.assertRedirects(reponse, self.fiche, fetch_redirect_response=False)
        affectation = Affectation.objects.get(utilisateur=self.cible)
        self.assertEqual((affectation.societe.code, affectation.role, affectation.accorde_par), ("mlp", "saisie", self.admin_groupe))
        entree = JournalSecurite.objects.get(evenement=E.ACCES_SOCIETE_ACCORDE)
        self.assertEqual((entree.utilisateur, entree.details["motif"]), (self.admin_groupe, "Remplacement"))

    def test_retrait_sans_motif_refuse(self):
        services.accorder_acces_societe(self.admin_groupe, self.cible, self.anl, "lecture")
        confirmer = {"bloc": "acces", "etape": "confirmer", **self.donnees_acces()}
        reponse = self.client.post(self.fiche, confirmer)
        self.assertContains(reponse, "Un motif est obligatoire", status_code=422)
        self.assertTrue(Affectation.objects.get(utilisateur=self.cible).actif)
        self.client.post(self.fiche, {**confirmer, "motif": "Changement de poste"})
        self.assertFalse(Affectation.objects.get(utilisateur=self.cible).actif)

    def test_resume_donner_et_retirer(self):
        services.accorder_acces_societe(self.admin_groupe, self.cible, self.anl, "lecture")
        reponse = self.client.post(self.fiche, self.donnees_acces(mlp="saisie"))
        self.assertContains(reponse, "donner Saisie sur MLP")
        self.assertContains(reponse, "retirer l&#x27;accès ANL")

    def test_aucun_changement(self):
        reponse = self.client.post(self.fiche, self.donnees_acces(), follow=True)
        self.assertContains(reponse, "Aucun changement")

    def test_vue_groupe_selection_et_motif(self):
        donnees = {"bloc": "vue_groupe", "autoriser": "on", "portee": "selection", "societes": ["ooa", "anl", "otl"],
                   "detail_autorise": "on"}
        self.assertContains(self.client.post(self.fiche, donnees), "accorder la Vue Groupe : sociétés OOA, ANL, OTL")
        self.assertFalse(HabilitationVueGroupe.objects.filter(utilisateur=self.cible).exists())  # rien avant confirmation
        self.client.post(self.fiche, {**donnees, "etape": "confirmer", "motif": "Pilotage trimestriel"})
        h = HabilitationVueGroupe.objects.get(utilisateur=self.cible)
        self.assertEqual({s.code for s in h.societes.all()}, {"ooa", "anl", "otl"})
        self.assertTrue(h.detail_autorise)

    def test_selection_d_une_seule_societe_refusee(self):
        reponse = self.client.post(self.fiche, {"bloc": "vue_groupe", "autoriser": "on", "portee": "selection",
                                                "societes": ["ooa"]})
        self.assertContains(reponse, "au moins 2 sociétés", status_code=422)

    def test_retirer_la_vue_groupe(self):
        services.accorder_vue_groupe(self.admin_groupe, self.cible, portee="toutes", motif="Test")
        reponse = self.client.post(self.fiche, {"bloc": "vue_groupe"})
        self.assertContains(reponse, "retirer la Vue Groupe")
        self.client.post(self.fiche, {"bloc": "vue_groupe", "etape": "confirmer", "motif": "Revue T4 2026"})
        self.assertFalse(HabilitationVueGroupe.objects.get(utilisateur=self.cible).actif)

    def test_activer_et_desactiver(self):
        self.client.post(self.fiche, {"bloc": "desactiver", "motif": "Départ"})
        self.cible.refresh_from_db()
        self.assertFalse(self.cible.is_active)
        self.client.post(self.fiche, {"bloc": "activer"})
        self.cible.refresh_from_db()
        self.assertTrue(self.cible.is_active)

    def test_role_global_non_retirable_sans_superutilisateur(self):
        autre = creer_utilisateur("admin2", "admin_groupe")
        url = reverse("interface:habilitation_fiche", args=[autre.pk])
        with self.assertLogs("securite", "WARNING"):
            self.client.post(url, {"bloc": "role_global", "role_global": "", "motif": "x"})
        autre.refresh_from_db()
        self.assertEqual(autre.role_global, "admin_groupe")


class ApercuTests(EcranBase):
    def verifier(self, utilisateur):
        apercu = logique.apercu_droits(utilisateur)
        frais = Utilisateur.objects.get(pk=utilisateur.pk)
        attendu = {s.code: acces.role_sur(frais, s) is not None for s in Societe.objects.filter(actif=True)}
        self.assertEqual({l["societe"].code: l["acces"] for l in apercu["lignes"]}, attendu)
        self.assertEqual(apercu["voit_groupe"], acces.voit_vue_groupe(frais))
        self.assertEqual({s.code for s in apercu["societes_groupe"]}, {s.code for s in acces.societes_vue_groupe(frais)})
        self.assertEqual(("Vue Groupe" in apercu["pages"]), acces.voit_vue_groupe(frais))
        return apercu

    def test_trois_profils_types(self):
        saisie = self.verifier(self.saisie_ooa)
        self.assertEqual([l["actions"] for l in saisie["lignes"] if l["acces"]], ["Lire et saisir"])
        direction = self.verifier(self.direction)
        self.assertTrue(direction["portee_toutes"] and direction["detail_groupe"])
        partiel = creer_utilisateur("partiel")
        services.accorder_vue_groupe(self.admin_groupe, partiel, portee="selection", societes=[self.ooa, self.anl],
                                     date_fin=timezone.localdate() + timedelta(days=5), motif="Test")
        apercu = self.verifier(partiel)
        self.assertEqual(len(apercu["societes_groupe"]), 2)
        self.assertFalse(any(l["acces"] for l in apercu["lignes"]))  # sans détail : aucune société ouvrable
        self.assertEqual(len(apercu["expirations"]), 1)

    def test_apercu_affiche_dans_la_fiche(self):
        services.accorder_acces_societe(self.admin_groupe, self.cible, self.ooa, "responsable")
        reponse = self.client.get(self.fiche)
        self.assertContains(reponse, "Ce que voit cette personne")
        self.assertContains(reponse, "Lire, saisir, gérer")
        self.assertContains(reponse, "2FA obligatoire")  # Responsable sans TOTP


class MatriceEtCreationTests(EcranBase):
    def test_matrice_et_csv(self):
        reponse = self.client.get(reverse("interface:habilitations_matrice"))
        self.assertContains(reponse, "La couleur ne porte jamais l")
        csv = self.client.get(reverse("interface:habilitations_matrice"), {"format": "csv"})
        self.assertEqual(csv["Content-Type"], "text/csv; charset=utf-8")
        lignes = csv.content.decode("utf-8-sig").splitlines()
        self.assertEqual(lignes[0], "Utilisateur;E-mail;OOA;ANL;OTL;ALON;MLP;Vue Groupe")
        direction = next(l for l in lignes if l.startswith("direction") or "direction@" in l)
        self.assertTrue(direction.endswith(";G;G;G;G;G;T"))
        resp = next(l for l in lignes if "resp_ooa@" in l)
        self.assertTrue(resp.endswith(";R;—;—;—;—;—"))

    def donnees(self, **extra):
        donnees = {"prenom": "Awa", "nom": "Kone", "email": "Awa.Kone@exemple.ci", "role_global": ""}
        for s in Societe.objects.filter(actif=True):
            donnees[f"role_{s.code}"] = ""
        donnees.update(extra)
        return donnees

    def test_creation_avec_habilitations_initiales(self):
        reponse = self.client.post(reverse("interface:habilitation_nouveau"), self.donnees(
            role_ooa="saisie", autoriser="on", portee="selection", societes=["ooa", "anl"], motif="Pilotage"))
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse["Cache-Control"], "no-store")
        utilisateur = Utilisateur.objects.get(email="awa.kone@exemple.ci")
        mot_de_passe = reponse.context["mot_de_passe"]
        self.assertContains(reponse, mot_de_passe)
        self.assertTrue(utilisateur.check_password(mot_de_passe))
        self.assertTrue(utilisateur.doit_changer_mot_de_passe)
        self.assertEqual(acces.role_sur(utilisateur, self.ooa), "saisie")
        self.assertTrue(acces.voit_vue_groupe(utilisateur))
        self.assertFalse(JournalSecurite.objects.filter(details__icontains=mot_de_passe).exists())  # jamais journalisé

    def test_creation_refusee_doublon_et_motif(self):
        reponse = self.client.post(reverse("interface:habilitation_nouveau"),
                                   self.donnees(email=self.saisie_ooa.email))
        self.assertContains(reponse, "existe déjà", status_code=422)
        reponse = self.client.post(reverse("interface:habilitation_nouveau"),
                                   self.donnees(autoriser="on", portee="toutes"))
        self.assertContains(reponse, "motif est obligatoire", status_code=422)
        self.assertFalse(Utilisateur.objects.filter(email="awa.kone@exemple.ci").exists())


class CommandesTests(EcranBase):
    def test_expirer_habilitations(self):
        hier = timezone.localdate() - timedelta(days=1)
        a = services.accorder_acces_societe(self.admin_groupe, self.cible, self.ooa, "lecture", date_fin=hier)
        h = services.accorder_vue_groupe(self.admin_groupe, self.cible, portee="toutes", date_fin=hier, motif="Test")
        durable = services.accorder_acces_societe(self.admin_groupe, self.saisie_anl, Societe.objects.get(code="otl"), "lecture")
        sortie = StringIO()
        call_command("expirer_habilitations", stdout=sortie)
        self.assertIn("2 habilitation(s)", sortie.getvalue())
        a.refresh_from_db(), h.refresh_from_db(), durable.refresh_from_db()
        self.assertFalse(a.actif or h.actif)
        self.assertTrue(durable.actif)
        self.assertEqual(JournalSecurite.objects.filter(evenement=E.HABILITATION_EXPIREE).count(), 2)
        call_command("expirer_habilitations", stdout=StringIO())  # idempotent
        self.assertEqual(JournalSecurite.objects.filter(evenement=E.HABILITATION_EXPIREE).count(), 2)

    def test_rapport_habilitations(self):
        services.accorder_acces_societe(self.admin_groupe, self.cible, self.ooa, "saisie", motif="Remplacement")
        services.accorder_acces_societe(self.admin_groupe, self.cible, self.anl, "lecture",
                                        date_fin=timezone.localdate() - timedelta(days=1))  # expirée : absente
        texte = StringIO()
        call_command("rapport_habilitations", stdout=texte)
        self.assertIn("accès société : ooa — Saisie", texte.getvalue())
        self.assertNotIn("anl — Lecture", texte.getvalue())
        sortie = StringIO()
        call_command("rapport_habilitations", "--format", "csv", stdout=sortie)
        lignes = sortie.getvalue().splitlines()
        self.assertTrue(lignes[0].startswith("email;nom;compte_actif"))
        self.assertTrue(any("cible@exemple.ci" in l and ";ooa;" in l and "Remplacement" in l for l in lignes))
        self.assertFalse(any("cible@exemple.ci" in l and ";anl;" in l for l in lignes))
        self.assertTrue(any("direction@exemple.ci" in l and "Vue Groupe" in l and "toutes les sociétés" in l for l in lignes))


class ApercuEnDirectTests(EcranBase):
    def url_apercu(self):
        return reverse("interface:habilitation_apercu", args=[self.cible.pk])

    def test_apercu_avec_modifications_non_enregistrees(self):
        donnees = self.donnees_acces(mlp="saisie")
        donnees.update(autoriser="on", portee="selection", societes=["ooa", "anl"], detail_autorise="on")
        reponse = self.client.get(self.url_apercu(), donnees, **HTMX)
        self.assertContains(reponse, "non enregistrées")
        self.assertContains(reponse, "OOA, ANL")
        self.assertContains(reponse, "avec accès au détail en lecture seule")
        self.assertContains(reponse, "Lire et saisir")
        # rien n'a été écrit
        self.assertFalse(Affectation.objects.filter(utilisateur=self.cible).exists())
        self.assertFalse(HabilitationVueGroupe.objects.filter(utilisateur=self.cible).exists())

    def test_apercu_simule_avec_acces_py(self):
        donnees = self.donnees_acces(ooa="responsable")
        reponse = self.client.get(self.url_apercu(), donnees, **HTMX)
        self.assertContains(reponse, "Lire, saisir, gérer")
        self.assertContains(reponse, "2FA obligatoire")  # Responsable sans 2FA

    def test_apercu_ignore_une_habilitation_expiree(self):
        hier = (timezone.localdate() - timedelta(days=1)).isoformat()
        donnees = self.donnees_acces(ooa="saisie")
        donnees["fin_ooa"] = hier
        reponse = self.client.get(self.url_apercu(), donnees, **HTMX)
        self.assertNotContains(reponse, "Lire et saisir")

    def test_apercu_reserve_a_l_admin(self):
        self.connecter(self.saisie_ooa)
        with self.assertLogs("securite", "WARNING"):
            self.assertEqual(self.client.get(self.url_apercu()).status_code, 404)

    def test_confirmation_htmx_en_fragment(self):
        reponse = self.client.post(self.fiche, self.donnees_acces(mlp="saisie"), **HTMX)
        self.assertContains(reponse, "donner Saisie sur MLP")
        self.assertNotContains(reponse, "<html")
        reponse = self.client.post(self.fiche, {"bloc": "vue_groupe", "autoriser": "on", "portee": "selection",
                                                "societes": ["ooa"]}, **HTMX)
        self.assertContains(reponse, "au moins 2 sociétés", status_code=422)
        self.assertNotContains(reponse, "<html", status_code=422)
        reponse = self.client.post(self.fiche, self.donnees_acces(), **HTMX)
        self.assertContains(reponse, "Aucun changement")
