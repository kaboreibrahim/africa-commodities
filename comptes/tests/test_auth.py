from io import StringIO

from allauth.account.models import EmailAddress
from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.urls import reverse

from comptes.models import Affectation, Utilisateur

from .jeu import MOT_DE_PASSE, JeuUtilisateursMixin, ReinitialiserAxesMixin, activer_totp

URL_CONNEXION = reverse("account_login")
URL_ADMIN = f"/{settings.ADMIN_URL}"


class InscriptionTests(TestCase):
    def test_inscription_publique_fermee(self):
        reponse = self.client.post(reverse("account_signup"), {
            "email": "pirate@exemple.ci", "password1": MOT_DE_PASSE, "password2": MOT_DE_PASSE,
        })
        self.assertEqual(reponse.status_code, 404)
        self.assertFalse(Utilisateur.objects.filter(email="pirate@exemple.ci").exists())


class ConnexionTests(ReinitialiserAxesMixin, JeuUtilisateursMixin, TestCase):
    def connecter(self, email, mot_de_passe):
        return self.client.post(URL_CONNEXION, {"login": email, "password": mot_de_passe})

    def test_connexion_par_email(self):
        reponse = self.connecter(self.saisie_ooa.email, MOT_DE_PASSE)
        self.assertRedirects(reponse, "/", fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.saisie_ooa.pk)

    def test_blocage_apres_5_echecs(self):
        for _ in range(5):
            reponse = self.connecter(self.saisie_ooa.email, "mauvais-mot-de-passe")
            self.assertNotIn("_auth_user_id", self.client.session)
        # 6e tentative, avec le BON mot de passe : toujours bloquée
        reponse = self.connecter(self.saisie_ooa.email, MOT_DE_PASSE)
        self.assertEqual(reponse.status_code, 429)
        self.assertTemplateUsed(reponse, "comptes/compte_bloque.html")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_blocage_insensible_a_la_casse_de_l_email(self):
        for i in range(5):
            email = self.saisie_ooa.email.upper() if i % 2 else self.saisie_ooa.email
            self.connecter(email, "mauvais-mot-de-passe")
        self.assertEqual(self.connecter(self.saisie_ooa.email, MOT_DE_PASSE).status_code, 429)

    def test_le_blocage_ne_touche_que_l_identifiant_vise(self):
        for _ in range(5):
            self.connecter(self.saisie_ooa.email, "mauvais-mot-de-passe")
        reponse = self.connecter(self.lecture_ooa.email, MOT_DE_PASSE)
        self.assertEqual(reponse.status_code, 302)

    def test_utilisateur_inactif_ne_peut_pas_se_connecter(self):
        self.connecter(self.inactif.email, MOT_DE_PASSE)
        self.assertNotIn("_auth_user_id", self.client.session)


class MFAObligatoireTests(ReinitialiserAxesMixin, JeuUtilisateursMixin, TestCase):
    def test_responsable_sans_totp_redirige_vers_l_activation(self):
        self.client.force_login(self.responsable_ooa)
        self.assertRedirects(self.client.get("/"), reverse("mfa_activate_totp"), fetch_redirect_response=False)

    def test_admin_groupe_sans_totp_redirige(self):
        self.client.force_login(self.admin_groupe)
        self.assertRedirects(self.client.get(URL_ADMIN), reverse("mfa_activate_totp"), fetch_redirect_response=False)

    def test_saisie_n_est_pas_redirige(self):
        self.client.force_login(self.saisie_ooa)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_pages_de_compte_accessibles_sans_totp(self):
        reponse = self.client.post(URL_CONNEXION, {"login": self.responsable_ooa.email, "password": MOT_DE_PASSE})
        self.assertRedirects(reponse, "/", fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("mfa_activate_totp")).status_code, 200)
        self.assertEqual(self.client.get(reverse("account_change_password")).status_code, 200)
        self.assertEqual(self.client.get(reverse("account_logout")).status_code, 200)

    def test_responsable_avec_totp_passe(self):
        activer_totp(self.responsable_ooa)
        self.client.force_login(self.responsable_ooa)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_connexion_avec_totp_demande_le_code(self):
        activer_totp(self.responsable_ooa)
        reponse = self.client.post(URL_CONNEXION, {"login": self.responsable_ooa.email, "password": MOT_DE_PASSE})
        self.assertRedirects(reponse, reverse("mfa_authenticate"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)


class AdminTests(ReinitialiserAxesMixin, JeuUtilisateursMixin, TestCase):
    def test_anonyme_redirige_vers_la_connexion_allauth(self):
        reponse = self.client.get(URL_ADMIN, follow=True)
        self.assertEqual(reponse.request["PATH_INFO"], URL_CONNEXION)
        self.assertTemplateUsed(reponse, "account/login.html")

    def test_formulaire_de_connexion_de_l_admin_desactive(self):
        reponse = self.client.post(f"{URL_ADMIN}login/", {"username": self.admin_groupe.username,
                                                          "password": MOT_DE_PASSE})
        self.assertTrue(reponse.url.startswith(URL_CONNEXION))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_saisie_connecte_n_accede_pas_a_l_admin(self):
        self.client.force_login(self.saisie_ooa)
        with self.assertLogs("securite", "WARNING"):
            reponse = self.client.get(URL_ADMIN, follow=True)
        self.assertEqual(reponse.status_code, 403)
        with self.assertLogs("securite", "WARNING"):
            self.assertEqual(self.client.get(f"{URL_ADMIN}operations/ligne/", follow=True).status_code, 403)

    def test_direction_n_accede_pas_a_l_admin(self):
        self.client.force_login(self.direction)
        with self.assertLogs("securite", "WARNING"):
            self.assertEqual(self.client.get(URL_ADMIN, follow=True).status_code, 403)

    def test_admin_groupe_avec_totp_accede_a_l_admin(self):
        activer_totp(self.admin_groupe)
        self.client.force_login(self.admin_groupe)
        self.assertEqual(self.client.get(URL_ADMIN).status_code, 200)
        self.assertEqual(self.client.get(f"{URL_ADMIN}comptes/utilisateur/").status_code, 200)


class MotDePasseProvisoireTests(ReinitialiserAxesMixin, JeuUtilisateursMixin, TestCase):
    def test_changement_impose(self):
        self.saisie_ooa.doit_changer_mot_de_passe = True
        self.saisie_ooa.save()
        self.client.force_login(self.saisie_ooa)
        url_mdp = reverse("account_change_password")
        self.assertRedirects(self.client.get("/"), url_mdp, fetch_redirect_response=False)
        self.assertRedirects(self.client.get(reverse("mfa_index")), url_mdp, fetch_redirect_response=False)
        self.assertEqual(self.client.get(url_mdp).status_code, 200)

        nouveau = "Un-Nouveau-Mot-De-Passe-2026"
        self.client.post(url_mdp, {"oldpassword": MOT_DE_PASSE, "password1": nouveau, "password2": nouveau})
        self.saisie_ooa.refresh_from_db()
        self.assertFalse(self.saisie_ooa.doit_changer_mot_de_passe)
        self.assertTrue(self.saisie_ooa.check_password(nouveau))


class CreerUtilisateurTests(TestCase):
    def test_creation(self):
        sortie = StringIO()
        call_command("creer_utilisateur", "--email", "Awa.Kone@Exemple.ci", "--nom", "Koné", "--prenom", "Awa",
                     "--societe", "ooa:responsable", "--societe", "anl:lecture", stdout=sortie)
        user = Utilisateur.objects.get(email="awa.kone@exemple.ci")
        self.assertTrue(user.doit_changer_mot_de_passe)
        self.assertEqual(dict(user.affectations.values_list("societe__code", "role")),
                         {"ooa": Affectation.Role.RESPONSABLE, "anl": Affectation.Role.LECTURE})
        mot_de_passe = sortie.getvalue().split("UNE SEULE FOIS")[1].splitlines()[1].strip()
        self.assertGreaterEqual(len(mot_de_passe), 20)
        self.assertTrue(user.check_password(mot_de_passe))
        self.assertTrue(EmailAddress.objects.filter(user=user, verified=True, primary=True).exists())

    def test_role_global(self):
        call_command("creer_utilisateur", "--email", "dg@exemple.ci", "--nom", "Diallo", "--prenom", "Moussa",
                     "--role-global", "admin_groupe", stdout=StringIO())
        self.assertTrue(Utilisateur.objects.get(email="dg@exemple.ci").is_staff)

    def test_erreurs(self):
        with self.assertRaises(CommandError):
            call_command("creer_utilisateur", "--email", "x@exemple.ci", "--nom", "X", "--prenom", "Y",
                         stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("creer_utilisateur", "--email", "x@exemple.ci", "--nom", "X", "--prenom", "Y",
                         "--societe", "zzz:saisie", stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("creer_utilisateur", "--email", "x@exemple.ci", "--nom", "X", "--prenom", "Y",
                         "--societe", "ooa:chef", stdout=StringIO())
        call_command("creer_utilisateur", "--email", "x@exemple.ci", "--nom", "X", "--prenom", "Y",
                     "--societe", "ooa:saisie", stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("creer_utilisateur", "--email", "X@exemple.ci", "--nom", "X", "--prenom", "Y",
                         "--societe", "ooa:saisie", stdout=StringIO())
