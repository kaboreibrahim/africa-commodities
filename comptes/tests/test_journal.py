import json
from datetime import date, timedelta
from io import StringIO

from allauth.mfa.models import Authenticator
from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comptes.models import Affectation, JournalSecurite, Utilisateur
from operations import services
from operations.models import Ligne
from repartition.models import RegleRepartition
from societes import services as services_societe
from societes.models import Client

from .jeu import MOT_DE_PASSE, JeuUtilisateursMixin, ReinitialiserAxesMixin, activer_totp

E = JournalSecurite.Evenement
URL_CONNEXION = reverse("account_login")


class JournalConnexionTests(ReinitialiserAxesMixin, JeuUtilisateursMixin, TestCase):
    def connecter(self, email, mot_de_passe):
        return self.client.post(URL_CONNEXION, {"login": email, "password": mot_de_passe},
                                HTTP_USER_AGENT="Navigateur de test")

    def test_connexion_reussie(self):
        self.connecter(self.saisie_ooa.email, MOT_DE_PASSE)
        entree = JournalSecurite.objects.get(evenement=E.CONNEXION)
        self.assertEqual(entree.utilisateur, self.saisie_ooa)
        self.assertEqual(entree.ip, "127.0.0.1")
        self.assertEqual(entree.user_agent, "Navigateur de test")

    def test_echec_de_connexion(self):
        self.connecter("Saisie_OOA@exemple.ci", "mauvais-mot-de-passe")
        entree = JournalSecurite.objects.get(evenement=E.ECHEC_CONNEXION)
        self.assertEqual(entree.identifiant_saisi, "saisie_ooa@exemple.ci")
        self.assertIsNone(entree.utilisateur)
        self.assertFalse(JournalSecurite.objects.filter(evenement=E.CONNEXION).exists())

    def test_blocage(self):
        for _ in range(5):
            self.connecter(self.saisie_ooa.email, "mauvais-mot-de-passe")
        entree = JournalSecurite.objects.get(evenement=E.COMPTE_BLOQUE)
        self.assertEqual(entree.utilisateur, self.saisie_ooa)
        self.assertEqual(entree.identifiant_saisi, self.saisie_ooa.email)
        self.connecter(self.saisie_ooa.email, MOT_DE_PASSE)  # bloqué malgré le bon mot de passe
        self.assertFalse(JournalSecurite.objects.filter(evenement=E.CONNEXION).exists())
        self.assertTrue(JournalSecurite.objects.filter(evenement=E.ECHEC_CONNEXION, details__bloque=True).exists())

    def test_deconnexion(self):
        self.client.force_login(self.saisie_ooa)
        self.client.post(reverse("account_logout"))
        self.assertTrue(JournalSecurite.objects.filter(evenement=E.DECONNEXION, utilisateur=self.saisie_ooa).exists())

    def test_aucun_secret_dans_le_journal(self):
        mauvais = "Mauvais-Mot-De-Passe-Secret-42"
        self.connecter(self.saisie_ooa.email, mauvais)
        self.connecter(self.saisie_ooa.email, MOT_DE_PASSE)
        nouveau = "Nouveau-Mot-De-Passe-Secret-2026"
        self.client.post(reverse("account_change_password"),
                         {"oldpassword": MOT_DE_PASSE, "password1": nouveau, "password2": nouveau})
        self.assertTrue(JournalSecurite.objects.filter(evenement=E.MOT_DE_PASSE_CHANGE).exists())
        contenu = json.dumps(list(JournalSecurite.objects.values()), default=str)
        for secret in (MOT_DE_PASSE, mauvais, nouveau, "pbkdf2", "argon2"):
            self.assertNotIn(secret, contenu)
        for entree in JournalSecurite.objects.all():
            self.assertNotIn(MOT_DE_PASSE, json.dumps(entree.details))


class JournalEvenementsTests(JeuUtilisateursMixin, TestCase):
    def setUp(self):
        JournalSecurite.objects.all().delete()  # entrées créées par le jeu d'utilisateurs

    def test_details_sensibles_filtres(self):
        from comptes.journal import journaliser

        journaliser(E.ACCES_REFUSE, utilisateur=self.saisie_ooa, password="x", code_totp="123456", token="t",
                    recovery_codes="a b", action="test")
        self.assertEqual(JournalSecurite.objects.get().details, {"action": "test"})

    def test_mfa_activee_puis_desactivee(self):
        activer_totp(self.saisie_ooa)
        self.assertTrue(JournalSecurite.objects.filter(evenement=E.MFA_ACTIVEE, utilisateur=self.saisie_ooa).exists())
        Authenticator.objects.filter(user=self.saisie_ooa).delete()
        self.assertTrue(JournalSecurite.objects.filter(evenement=E.MFA_DESACTIVEE, utilisateur=self.saisie_ooa).exists())

    def test_role_global_et_affectations(self):
        self.lecture_ooa.role_global = Utilisateur.RoleGlobal.ADMIN_GROUPE
        self.lecture_ooa.save()
        entree = JournalSecurite.objects.get(evenement=E.ROLE_MODIFIE)
        self.assertEqual(entree.details["role_global_apres"], "admin_groupe")

        affectation = Affectation.objects.create(utilisateur=self.lecture_ooa, societe=self.anl, role="saisie")
        affectation.role = "responsable"
        affectation.save()
        affectation.delete()
        actions = list(JournalSecurite.objects.filter(evenement=E.ROLE_MODIFIE, details__has_key="action")
                       .order_by("id").values_list("details__action", flat=True))
        self.assertEqual(actions, ["creee", "modifiee", "supprimee"])

    def test_suppression_d_un_utilisateur_avec_affectations(self):
        self.affectation_inactive.delete()
        self.assertTrue(JournalSecurite.objects.filter(identifiant_saisi=self.affectation_inactive.email,
                                                       details__action="supprimee").exists())

    def test_refus_de_service_journalise(self):
        from django.core.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied), self.assertLogs("securite", "WARNING"):
            services.creer_ligne(self.lecture_ooa, self.ooa, date=timezone.localdate(), reference="X",
                                 quantite=1, marge_unitaire=1)
        entree = JournalSecurite.objects.get(evenement=E.ACCES_REFUSE)
        self.assertEqual((entree.utilisateur, entree.details["action"]), (self.lecture_ooa, "creer_ligne"))


class JournalRequeteTests(ReinitialiserAxesMixin, JeuUtilisateursMixin, TestCase):
    def test_refus_dans_une_vue_survit_a_la_transaction_annulee(self):
        """ATOMIC_REQUESTS annule la transaction de la vue : le journal est écrit après."""
        self.client.force_login(self.saisie_ooa)
        with self.assertLogs("securite", "WARNING"):
            reponse = self.client.get(f"/{settings.ADMIN_URL}", follow=True)
        self.assertEqual(reponse.status_code, 403)
        entree = JournalSecurite.objects.get(evenement=E.ACCES_REFUSE)
        self.assertEqual((entree.utilisateur, entree.details["action"], entree.ip),
                         (self.saisie_ooa, "admin", "127.0.0.1"))


class HistoriqueTests(JeuUtilisateursMixin, TestCase):
    def test_modification_d_une_ligne_historisee_avec_l_auteur(self):
        services.modifier_ligne(self.responsable_ooa, self.ligne_saisie_ooa, quantite=4)
        derniere = self.ligne_saisie_ooa.history.first()
        self.assertEqual(derniere.history_type, "~")
        self.assertEqual(derniere.history_user, self.responsable_ooa)
        self.assertEqual(derniere.quantite, 4)
        self.assertEqual(self.ligne_saisie_ooa.history.last().history_type, "+")

    def test_suppression_douce_historisee(self):
        services.supprimer_ligne(self.responsable_ooa, self.ligne_saisie_ooa)
        derniere = self.ligne_saisie_ooa.history.first()
        self.assertIsNotNone(derniere.supprime_le)
        self.assertEqual(derniere.history_user, self.responsable_ooa)
        services.restaurer_ligne(self.admin_groupe, Ligne.tous.get(pk=self.ligne_saisie_ooa.pk))
        self.assertIsNone(self.ligne_saisie_ooa.history.first().supprime_le)

    def test_historique_via_une_requete(self):
        """Dans une requête, l'auteur vient de la requête (middleware de simple_history)."""
        activer_totp(self.admin_groupe)
        self.client.force_login(self.admin_groupe)
        url = f"/{settings.ADMIN_URL}operations/ligne/{self.ligne_anl.pk}/change/"
        self.client.post(url, {"date": self.ligne_anl.date.strftime("%d/%m/%Y"), "reference": "MODIFIEE",
                               "quantite": 1, "marge_unitaire": 100_000, "extra": "", "projet": "",
                               "observation": "", "client": ""})
        self.assertEqual(self.ligne_anl.history.first().history_user, self.admin_groupe)
        self.assertEqual(self.client.get(f"{url.rsplit('change/', 1)[0]}history/").status_code, 200)

    def test_clients_objectifs_affectations_utilisateurs(self):
        client = services_societe.ajouter_client(self.responsable_ooa, self.ooa, "PALMCI")
        services_societe.retirer_client(self.responsable_ooa, client)
        self.assertEqual([h.history_user for h in Client.tous.get(pk=client.pk).history.all()],
                         [self.responsable_ooa, self.responsable_ooa])
        objectif = services_societe.definir_objectif(self.responsable_ooa, self.ooa, timezone.localdate(), 5)
        self.assertEqual(objectif.history.first().history_user, self.responsable_ooa)
        self.assertTrue(Affectation.history.filter(utilisateur=self.saisie_ooa).exists())
        self.ooa.nom = "Oils of Africa SA"
        self.ooa.save()
        self.assertEqual(self.ooa.history.first().nom, "Oils of Africa SA")
        regle = RegleRepartition.objects.create(date_debut=date(2030, 1, 1))
        self.assertEqual(regle.history.count(), 1)

    def test_le_mot_de_passe_n_est_jamais_historise(self):
        champs = {f.name for f in Utilisateur.history.model._meta.get_fields()}
        self.assertNotIn("password", champs)
        self.assertNotIn("last_login", champs)
        self.saisie_ooa.set_password("Autre-Mot-De-Passe-123")
        self.saisie_ooa.save()
        self.assertEqual(self.saisie_ooa.history.count(), 2)

    def test_last_login_ne_cree_pas_d_historique(self):
        avant = self.saisie_ooa.history.count()
        self.saisie_ooa.last_login = timezone.now()
        self.saisie_ooa.save(update_fields=["last_login"])
        self.assertEqual(self.saisie_ooa.history.count(), avant)


class PurgerJournalTests(TestCase):
    def test_purge(self):
        ancienne = JournalSecurite.objects.create(evenement=E.CONNEXION)
        JournalSecurite.objects.filter(pk=ancienne.pk).update(date=timezone.now() - timedelta(days=400))
        recente = JournalSecurite.objects.create(evenement=E.CONNEXION)
        call_command("purger_journal", "--jours", "365", stdout=StringIO())
        self.assertEqual(list(JournalSecurite.objects.all()), [recente])
        with self.assertRaises(CommandError):
            call_command("purger_journal", "--jours", "1", stdout=StringIO())
