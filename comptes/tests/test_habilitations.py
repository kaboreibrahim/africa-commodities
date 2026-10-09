"""Habilitations : accès société et Vue Groupe accordés par l'admin groupe (portée, détail, dates, services, journal)."""
import importlib
from datetime import timedelta
from decimal import Decimal

from allauth.mfa.models import Authenticator
from django.apps import apps
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comptes import acces, services
from comptes.models import Affectation, HabilitationVueGroupe, JournalSecurite, Utilisateur
from interface.tests.outils import compter_requetes
from societes.models import Societe

from .jeu import JeuUtilisateursMixin, ReinitialiserAxesMixin, activer_totp, creer_ligne, creer_utilisateur

E = JournalSecurite.Evenement
PORTEE = HabilitationVueGroupe.Portee
URL_GROUPE = "/groupe/"


class HabilitationsBase(ReinitialiserAxesMixin, JeuUtilisateursMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.otl = Societe.objects.get(code="otl")
        cls.alon = Societe.objects.get(code="alon")
        cls.mlp = Societe.objects.get(code="mlp")
        # Marges du mois : OOA 200 000 (2 lignes du jeu), ANL 100 000, puis OTL 300 000, ALON 400 000, MLP 500 000.
        creer_ligne(cls.otl, cls.admin_groupe, marge_unitaire=300_000)
        creer_ligne(cls.alon, cls.admin_groupe, marge_unitaire=400_000)
        creer_ligne(cls.mlp, cls.admin_groupe, marge_unitaire=500_000)
        cls.aujourd_hui = timezone.localdate()

    def setUp(self):
        super().setUp()
        cache.clear()
        self.rien = creer_utilisateur("rien")
        self.admin = self.admin_groupe

    def vue_groupe(self, utilisateur=None, societes=None, **options):
        """Accorde la Vue Groupe (par le service) ; 2FA activée car obligatoire pour les titulaires."""
        utilisateur = utilisateur or self.rien
        options.setdefault("motif", "Test")
        options.setdefault("portee", PORTEE.SELECTION if societes else PORTEE.TOUTES)
        habilitation = services.accorder_vue_groupe(self.admin, utilisateur, societes=societes or (), **options)
        self.totp(utilisateur)
        return habilitation

    @staticmethod
    def totp(utilisateur):
        if not Authenticator.objects.filter(user=utilisateur, type=Authenticator.Type.TOTP).exists():
            activer_totp(utilisateur)

    def ouvrir(self, utilisateur, url):
        self.client.force_login(utilisateur)
        return self.client.get(url)


class PorteeTests(HabilitationsBase):
    def test_sans_habilitation_rien_n_est_visible(self):
        self.assertFalse(acces.voit_vue_groupe(self.rien))
        self.assertFalse(acces.societes_accessibles(self.rien).exists())
        self.assertFalse(acces.societes_vue_groupe(self.rien).exists())
        self.assertEqual(self.ouvrir(self.rien, URL_GROUPE).status_code, 404)

    def test_selection_exclut_les_autres_societes(self):
        self.vue_groupe(societes=[self.ooa, self.anl, self.otl])
        self.assertEqual({s.code for s in acces.societes_vue_groupe(self.rien)}, {"ooa", "anl", "otl"})
        reponse = self.ouvrir(self.rien, URL_GROUPE)
        self.assertEqual(reponse.status_code, 200)
        total = reponse.context["total"]
        self.assertEqual(total["marge"], Decimal(600_000))  # OOA 200 000 + ANL 100 000 + OTL 300 000 (ni ALON ni MLP)
        self.assertEqual(len(reponse.context["synthese"]), 3)
        self.assertContains(reponse, "Vue Groupe — 3 sociétés : OOA, ANL, OTL")
        self.assertContains(reponse, "/ 3")  # « x / 3 sociétés à l'objectif »
        self.assertNotContains(reponse, "Alon")
        self.assertNotContains(reponse, "Mon Livreur")

    def test_portee_toutes_inclut_une_societe_creee_ensuite(self):
        self.vue_groupe()
        self.assertEqual(len(self.ouvrir(self.rien, URL_GROUPE).context["synthese"]), 5)
        Societe.objects.create(code="nouv", nom="Nouvelle société")
        reponse = self.client.get(URL_GROUPE)
        self.assertEqual(len(reponse.context["synthese"]), 6)
        self.assertContains(reponse, "toutes les sociétés")

    def test_sans_detail_pas_d_acces_aux_societes(self):
        self.vue_groupe(societes=[self.ooa, self.anl], detail_autorise=False)
        reponse = self.ouvrir(self.rien, URL_GROUPE)
        self.assertNotContains(reponse, "data-href")  # lignes non cliquables
        self.assertNotContains(reponse, 'href="/s/ooa/"')
        self.assertEqual(self.client.get("/s/ooa/").status_code, 404)
        self.assertEqual(self.client.get("/s/ooa/lignes/").status_code, 404)
        self.assertIsNone(acces.role_sur(self.rien, self.ooa))

    def test_avec_detail_lecture_seule(self):
        self.vue_groupe(societes=[self.ooa, self.anl], detail_autorise=True)
        self.assertContains(self.ouvrir(self.rien, URL_GROUPE), 'data-href="/s/ooa/"')
        self.assertEqual(self.client.get("/s/ooa/").status_code, 200)
        self.assertEqual(self.client.get("/s/ooa/lignes/").status_code, 200)
        self.assertEqual(self.client.get("/s/otl/").status_code, 404)  # hors portée
        self.assertEqual(acces.role_sur(self.rien, self.ooa), "lecture_groupe")
        self.assertFalse(acces.peut_saisir(self.rien, self.ooa))
        self.assertFalse(acces.peut_gerer_societe(self.rien, self.ooa))
        for url in ("/s/ooa/lignes/", "/s/ooa/objectif/", "/s/ooa/depenses/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url, {}).status_code, 403)

    def test_saisie_sur_ooa_et_vue_groupe_sans_detail(self):
        Affectation.objects.create(utilisateur=self.rien, societe=self.ooa, role=Affectation.Role.SAISIE)
        self.vue_groupe(societes=[self.ooa, self.anl, self.mlp])
        self.assertEqual(acces.role_sur(self.rien, self.ooa), "saisie")
        self.assertTrue(acces.peut_saisir(self.rien, self.ooa))
        self.assertIsNone(acces.role_sur(self.rien, self.anl))
        self.assertEqual({s.code for s in acces.societes_accessibles(self.rien)}, {"ooa"})
        reponse = self.ouvrir(self.rien, URL_GROUPE)
        self.assertContains(reponse, 'data-href="/s/ooa/"')       # son accès OOA reste cliquable
        self.assertNotContains(reponse, 'data-href="/s/anl/"')    # ANL : chiffres consolidés seulement
        self.assertNotContains(reponse, 'data-href="/s/mlp/"')
        self.assertEqual(self.client.get("/s/anl/").status_code, 404)

    def test_couleurs_du_theme_pour_la_vue_groupe_sans_detail(self):
        self.vue_groupe(societes=[self.ooa, self.anl])
        css = self.ouvrir(self.rien, "/theme/groupe.css").content.decode()
        self.assertIn(".serie-ooa", css)
        self.assertNotIn(".serie-otl", css)


class DatesTests(HabilitationsBase):
    def test_vue_groupe_pas_encore_valable_ou_expiree(self):
        demain, hier = self.aujourd_hui + timedelta(days=1), self.aujourd_hui - timedelta(days=1)
        for options in ({"date_debut": demain}, {"date_fin": hier}):
            with self.subTest(**{k: str(v) for k, v in options.items()}):
                self.vue_groupe(**options)
                acces.vider_cache(self.rien)
                self.assertFalse(acces.voit_vue_groupe(self.rien))
                self.assertEqual(self.ouvrir(self.rien, URL_GROUPE).status_code, 404)

    def test_vue_groupe_valable_aujourd_hui(self):
        self.vue_groupe(date_debut=self.aujourd_hui, date_fin=self.aujourd_hui)  # bornes incluses
        self.assertTrue(acces.voit_vue_groupe(self.rien))

    def test_affectation_pas_encore_valable_ou_expiree(self):
        demain, hier = self.aujourd_hui + timedelta(days=1), self.aujourd_hui - timedelta(days=1)
        for options in ({"date_debut": demain}, {"date_fin": hier}):
            with self.subTest(**{k: str(v) for k, v in options.items()}):
                services.accorder_acces_societe(self.admin, self.rien, self.ooa, "saisie", **options)
                acces.vider_cache(self.rien)
                self.assertIsNone(acces.role_sur(self.rien, self.ooa))
                self.assertFalse(acces.societes_accessibles(self.rien).exists())
                self.assertEqual(self.ouvrir(self.rien, "/s/ooa/").status_code, 404)

    def test_affectation_en_vigueur(self):
        affectation = services.accorder_acces_societe(
            self.admin, self.rien, self.ooa, "saisie", date_debut=self.aujourd_hui - timedelta(days=3),
            date_fin=self.aujourd_hui + timedelta(days=3))
        self.assertTrue(affectation.est_en_vigueur())
        self.assertFalse(affectation.est_en_vigueur(self.aujourd_hui + timedelta(days=4)))
        self.assertEqual(acces.role_sur(self.rien, self.ooa), "saisie")

    def test_contraintes_de_dates_en_base(self):
        with self.assertRaises(ValidationError):
            services.accorder_acces_societe(self.admin, self.rien, self.ooa, "lecture",
                                            date_debut=self.aujourd_hui, date_fin=self.aujourd_hui - timedelta(days=1))


class RetraitTests(HabilitationsBase):
    def test_retrait_vue_groupe_effet_immediat_et_sessions_supprimees(self):
        self.vue_groupe(societes=[self.ooa, self.anl])
        self.assertEqual(self.ouvrir(self.rien, URL_GROUPE).status_code, 200)
        self.assertEqual(Session.objects.count(), 1)
        services.retirer_vue_groupe(self.admin, self.rien, motif="Fin de mission")
        self.assertEqual(Session.objects.count(), 0)
        self.assertNotEqual(self.client.get(URL_GROUPE).status_code, 200)  # déconnecté : redirigé vers la connexion

    def test_sans_suppression_de_session_la_vue_groupe_devient_une_404(self):
        habilitation = self.vue_groupe()
        self.assertEqual(self.ouvrir(self.rien, URL_GROUPE).status_code, 200)
        HabilitationVueGroupe.objects.filter(pk=habilitation.pk).update(actif=False)  # modification directe en base
        self.assertEqual(self.client.get(URL_GROUPE).status_code, 404)  # dès la requête suivante, sans déconnexion

    def test_retrait_acces_societe(self):
        affectation = services.accorder_acces_societe(self.admin, self.rien, self.ooa, "saisie")
        self.client.force_login(self.rien)
        services.retirer_acces_societe(self.admin, affectation, motif="Changement de poste")
        affectation.refresh_from_db()
        self.assertFalse(affectation.actif)  # désactivée, jamais supprimée
        self.assertEqual(Session.objects.count(), 0)
        acces.vider_cache(self.rien)
        self.assertIsNone(acces.role_sur(self.rien, self.ooa))


class ServicesTests(HabilitationsBase):
    def test_un_non_admin_est_refuse_et_journalise(self):
        intrus = self.responsable_ooa
        appels = [
            lambda: services.accorder_acces_societe(intrus, self.rien, self.anl, "lecture"),
            lambda: services.modifier_acces_societe(intrus, self.affectation_ooa(), role="lecture"),
            lambda: services.retirer_acces_societe(intrus, self.affectation_ooa(), motif="x"),
            lambda: services.accorder_vue_groupe(intrus, self.rien, portee="toutes", motif="x"),
            lambda: services.modifier_vue_groupe(intrus, self.habilitation_existante(), detail_autorise=True),
            lambda: services.retirer_vue_groupe(intrus, self.direction, motif="x"),
            lambda: services.definir_role_global(intrus, self.rien, "admin_groupe"),
            lambda: services.activer_compte(intrus, self.rien),
            lambda: services.desactiver_compte(intrus, self.rien, motif="x"),
            lambda: services.creer_compte(intrus, email="a@b.ci", nom="A", prenom="B"),
        ]
        for i, appel in enumerate(appels):
            with self.subTest(service=i):
                avant = JournalSecurite.objects.filter(evenement=E.ACCES_REFUSE).count()
                with self.assertLogs("securite", "WARNING"), self.assertRaises(PermissionDenied):
                    appel()
                self.assertEqual(JournalSecurite.objects.filter(evenement=E.ACCES_REFUSE).count(), avant + 1)
        self.assertFalse(HabilitationVueGroupe.objects.filter(utilisateur=self.rien).exists())

    def affectation_ooa(self):
        return Affectation.objects.get(utilisateur=self.saisie_ooa, societe=self.ooa)

    def habilitation_existante(self):
        return HabilitationVueGroupe.objects.get(utilisateur=self.direction)

    def test_un_admin_ne_peut_pas_se_retirer_ses_droits_ni_se_desactiver(self):
        with self.assertRaisesMessage(ValidationError, "propres droits"):
            services.definir_role_global(self.admin, self.admin, "", motif="x")
        with self.assertRaisesMessage(ValidationError, "propre compte"):
            services.desactiver_compte(self.admin, self.admin, motif="x")
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role_global, "admin_groupe")
        self.assertTrue(self.admin.is_active)

    def test_retirer_le_role_admin_d_un_autre_est_reserve_au_superutilisateur(self):
        autre = creer_utilisateur("admin2", "admin_groupe")
        with self.assertLogs("securite", "WARNING"), self.assertRaises(PermissionDenied):
            services.definir_role_global(self.admin, autre, "", motif="x")
        root = Utilisateur.objects.create_superuser("root", "root@exemple.ci", "x")
        services.definir_role_global(root, autre, "", motif="Départ")
        self.assertEqual(Utilisateur.objects.get(pk=autre.pk).role_global, "")

    def test_le_dernier_admin_est_compte(self):
        self.assertEqual(services._admins_actifs_hors(self.admin), 0)  # seul admin : la règle « au moins un » l'interdit
        autre = creer_utilisateur("admin2", "admin_groupe")
        self.assertEqual(services._admins_actifs_hors(self.admin), 1)
        Utilisateur.objects.filter(pk=autre.pk).update(is_active=False)
        self.assertEqual(services._admins_actifs_hors(self.admin), 0)  # un admin inactif ne compte pas

    def test_selection_de_moins_de_2_societes_refusee(self):
        for societes in ([], [self.ooa], [self.ooa, self.ooa]):
            with self.subTest(n=len(societes)), self.assertRaisesMessage(ValidationError, "au moins 2 sociétés"):
                services.accorder_vue_groupe(self.admin, self.rien, portee="selection", societes=societes, motif="x")
        self.assertFalse(HabilitationVueGroupe.objects.filter(utilisateur=self.rien).exists())

    def test_motifs_obligatoires(self):
        with self.assertRaisesMessage(ValidationError, "motif"):
            services.accorder_vue_groupe(self.admin, self.rien, portee="toutes", motif="  ")
        affectation = services.accorder_acces_societe(self.admin, self.rien, self.ooa, "lecture")  # motif facultatif
        with self.assertRaisesMessage(ValidationError, "motif"):
            services.retirer_acces_societe(self.admin, affectation, motif="")
        self.vue_groupe()
        with self.assertRaisesMessage(ValidationError, "motif"):
            services.retirer_vue_groupe(self.admin, self.rien, motif="")
        with self.assertRaisesMessage(ValidationError, "motif"):
            services.desactiver_compte(self.admin, self.rien, motif="")

    def test_desactiver_un_compte_supprime_ses_sessions(self):
        self.client.force_login(self.rien)
        self.assertEqual(Session.objects.count(), 1)
        services.desactiver_compte(self.admin, self.rien, motif="Départ")
        self.assertEqual(Session.objects.count(), 0)
        self.rien.refresh_from_db()
        self.assertFalse(self.rien.is_active)
        services.activer_compte(self.admin, self.rien)
        self.rien.refresh_from_db()
        self.assertTrue(self.rien.is_active)

    def test_journal_de_chaque_service(self):
        affectation = services.accorder_acces_societe(self.admin, self.rien, self.ooa, "saisie",
                                                      date_fin=self.aujourd_hui + timedelta(days=30), motif="Remplacement")
        entree = JournalSecurite.objects.get(evenement=E.ACCES_SOCIETE_ACCORDE)
        self.assertEqual(entree.utilisateur, self.admin)
        self.assertEqual(entree.details["cible_email"], self.rien.email)
        self.assertEqual(entree.details["motif"], "Remplacement")
        self.assertIsNone(entree.details["avant"])
        self.assertEqual(entree.details["apres"]["role"], "saisie")

        services.modifier_acces_societe(self.admin, affectation, role="responsable")
        entree = JournalSecurite.objects.get(evenement=E.ACCES_SOCIETE_MODIFIE)
        self.assertEqual((entree.details["avant"]["role"], entree.details["apres"]["role"]), ("saisie", "responsable"))

        services.retirer_acces_societe(self.admin, affectation, motif="Fin")
        entree = JournalSecurite.objects.get(evenement=E.ACCES_SOCIETE_RETIRE)
        self.assertEqual((entree.details["avant"]["actif"], entree.details["apres"]["actif"], entree.details["motif"]),
                         (True, False, "Fin"))

        habilitation = services.accorder_vue_groupe(self.admin, self.rien, portee="selection",
                                                    societes=[self.ooa, self.anl], motif="Pilotage")
        entree = JournalSecurite.objects.get(evenement=E.VUE_GROUPE_ACCORDEE)
        self.assertEqual(entree.details["apres"]["societes"], ["anl", "ooa"])
        self.assertEqual(entree.details["apres"]["portee"], "selection")

        services.modifier_vue_groupe(self.admin, habilitation, societes=[self.ooa, self.anl, self.otl], detail_autorise=True)
        entree = JournalSecurite.objects.get(evenement=E.VUE_GROUPE_MODIFIEE)
        self.assertEqual(entree.details["avant"]["societes"], ["anl", "ooa"])
        self.assertEqual(entree.details["apres"]["societes"], ["anl", "ooa", "otl"])
        self.assertTrue(entree.details["apres"]["detail_autorise"])

        services.retirer_vue_groupe(self.admin, self.rien, motif="Revue T4 2026")
        entree = JournalSecurite.objects.get(evenement=E.VUE_GROUPE_RETIREE)
        self.assertEqual((entree.details["motif"], entree.details["apres"]["actif"]), ("Revue T4 2026", False))

        services.definir_role_global(self.admin, self.rien, "admin_groupe")
        entree = JournalSecurite.objects.get(evenement=E.ROLE_GLOBAL_MODIFIE)
        self.assertEqual((entree.details["avant"]["role_global"], entree.details["apres"]["role_global"]),
                         ("aucun", "admin_groupe"))

        services.desactiver_compte(self.admin, self.saisie_anl, motif="Départ")
        services.activer_compte(self.admin, self.saisie_anl)
        self.assertTrue(JournalSecurite.objects.filter(evenement=E.COMPTE_DESACTIVE, details__motif="Départ").exists())
        self.assertTrue(JournalSecurite.objects.filter(evenement=E.COMPTE_ACTIVE).exists())
        # Les signaux de modèle n'ajoutent pas de doublon quand l'opération passe par un service.
        self.assertFalse(JournalSecurite.objects.filter(evenement=E.ROLE_MODIFIE, utilisateur=self.rien).exists())

    def test_accorder_deux_fois_met_a_jour_au_lieu_de_dupliquer(self):
        services.accorder_acces_societe(self.admin, self.rien, self.ooa, "lecture")
        services.accorder_acces_societe(self.admin, self.rien, self.ooa, "saisie")
        self.assertEqual(Affectation.objects.filter(utilisateur=self.rien, societe=self.ooa).count(), 1)
        self.assertEqual(Affectation.objects.get(utilisateur=self.rien).accorde_par, self.admin)

    def test_creer_compte(self):
        utilisateur, mot_de_passe = services.creer_compte(
            self.admin, email="Nouveau@Exemple.ci", nom="Kone", prenom="Awa",
            acces_societes=[{"societe": self.ooa, "role": "saisie"}],
            vue_groupe={"portee": "selection", "societes": [self.ooa, self.anl], "motif": "Pilotage"})
        self.assertEqual(utilisateur.email, "nouveau@exemple.ci")
        self.assertTrue(utilisateur.doit_changer_mot_de_passe)
        self.assertTrue(utilisateur.check_password(mot_de_passe))
        self.assertEqual(acces.role_sur(utilisateur, self.ooa), "saisie")
        self.assertTrue(acces.voit_vue_groupe(utilisateur))
        self.assertTrue(JournalSecurite.objects.filter(evenement=E.COMPTE_CREE).exists())
        with self.assertRaisesMessage(ValidationError, "existe déjà"):
            services.creer_compte(self.admin, email="nouveau@exemple.ci", nom="K", prenom="A")


class MigrationEtMfaTests(HabilitationsBase):
    def test_migration_direction_vers_habilitation(self):
        migration = importlib.import_module("comptes.migrations.0006_reprise_role_direction")
        ancien = creer_utilisateur("ancien_dg")
        inactif = creer_utilisateur("ancien_inactif", is_active=False)
        Utilisateur.objects.filter(pk__in=[ancien.pk, inactif.pk]).update(role_global="direction")
        migration.direction_vers_habilitation(apps, None)
        habilitation = HabilitationVueGroupe.objects.get(utilisateur=ancien)
        self.assertEqual((habilitation.portee, habilitation.detail_autorise, habilitation.motif),
                         ("toutes", True, "Reprise automatique du rôle Direction"))
        self.assertFalse(HabilitationVueGroupe.objects.filter(utilisateur=inactif).exists())  # seuls les actifs
        self.assertEqual(Utilisateur.objects.get(pk=ancien.pk).role_global, "")
        acces.vider_cache(ancien)
        self.assertTrue(acces.voit_vue_groupe(ancien))
        self.assertEqual(acces.role_sur(ancien, self.ooa), "lecture_groupe")
        # Annulation de la migration
        migration.habilitation_vers_direction(apps, None)
        self.assertEqual(Utilisateur.objects.get(pk=ancien.pk).role_global, "direction")
        self.assertFalse(HabilitationVueGroupe.objects.filter(utilisateur=ancien).exists())

    def test_titulaire_sans_totp_redirige_vers_l_activation(self):
        services.accorder_vue_groupe(self.admin, self.rien, portee="toutes", motif="Test")
        self.client.force_login(self.rien)
        reponse = self.client.get(URL_GROUPE)
        self.assertRedirects(reponse, reverse("mfa_activate_totp"), fetch_redirect_response=False)
        self.totp(self.rien)
        self.assertEqual(self.client.get(URL_GROUPE).status_code, 200)

    def test_vue_groupe_expiree_n_impose_plus_la_2fa(self):
        services.accorder_vue_groupe(self.admin, self.rien, portee="toutes", motif="Test",
                                     date_fin=self.aujourd_hui - timedelta(days=1))
        self.assertNotIn("vue_groupe", acces.roles_de(self.rien))


class PerformanceTests(HabilitationsBase):
    def test_droits_en_une_requete_par_requete_http(self):
        self.vue_groupe(societes=[self.ooa, self.anl], detail_autorise=True)
        acces.vider_cache(self.rien)
        with self.assertNumQueries(1):
            for _ in range(20):
                acces.role_sur(self.rien, self.ooa)
                acces.voit_vue_groupe(self.rien)
                acces.detail_via_groupe(self.rien, self.anl)
                acces.roles_de(self.rien)

    def test_limite_de_requetes_de_la_vue_groupe(self):
        for utilisateur, societes in ((self.rien, [self.ooa, self.anl, self.otl]), (self.admin, None)):
            with self.subTest(utilisateur=utilisateur.username):
                if societes:
                    self.vue_groupe(societes=societes, detail_autorise=True)
                else:
                    self.totp(utilisateur)
                self.client.force_login(utilisateur)
                self.client.get(URL_GROUPE)
                with compter_requetes() as compte:
                    self.assertEqual(self.client.get(URL_GROUPE).status_code, 200)
                self.assertLessEqual(compte["nombre"], 12, "\n".join(compte["requetes"]))
