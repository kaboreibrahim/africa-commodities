from django.contrib import admin
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.views import View

from comptes import acces
from comptes.mixins import AccesSocieteMixin, SaisieSocieteMixin, VueGroupeMixin
from comptes.models import Affectation
from operations.models import Ligne
from societes.models import Client, ObjectifMensuel, Societe

from .jeu import JeuUtilisateursMixin, mois_decale

ROLES = ["admin_groupe", "direction", "responsable_ooa", "saisie_ooa", "lecture_ooa", "saisie_anl",
         "inactif", "affectation_inactive"]


def _site_admin(user):
    requete = RequestFactory().get("/")
    requete.user = user
    return admin.site.has_permission(requete)


# Matrice des droits (README, section Sécurité) : action -> rôles autorisés. Évaluée sur OOA.
MATRICE = {
    "voir OOA": (lambda t, u: acces.peut_lire(u, t.ooa),
                 {"admin_groupe", "direction", "responsable_ooa", "saisie_ooa", "lecture_ooa"}),
    "voir ANL": (lambda t, u: acces.peut_lire(u, t.anl), {"admin_groupe", "direction", "saisie_anl"}),
    "vue groupe": (lambda t, u: acces.voit_tout_le_groupe(u), {"admin_groupe", "direction"}),
    "ajouter une ligne": (lambda t, u: acces.peut_saisir(u, t.ooa), {"admin_groupe", "responsable_ooa", "saisie_ooa"}),
    "modifier la ligne de la saisie OOA": (lambda t, u: acces.peut_modifier_ligne(u, t.ligne_saisie_ooa),
                                           {"admin_groupe", "responsable_ooa", "saisie_ooa"}),
    "modifier la ligne d'un collègue": (lambda t, u: acces.peut_modifier_ligne(u, t.ligne_collegue),
                                        {"admin_groupe", "responsable_ooa"}),
    "modifier une ligne de 3 mois": (lambda t, u: acces.peut_modifier_ligne(u, t.ligne_ancienne),
                                     {"admin_groupe", "responsable_ooa"}),
    "supprimer / restaurer une ligne": (lambda t, u: acces.peut_supprimer_ligne(u, t.ligne_saisie_ooa),
                                        {"admin_groupe", "responsable_ooa"}),
    "gérer clients et objectifs": (lambda t, u: acces.peut_gerer_societe(u, t.ooa), {"admin_groupe", "responsable_ooa"}),
    "règle, sociétés, utilisateurs, affectations": (lambda t, u: acces.peut_administrer(u), {"admin_groupe"}),
    "accès à l'admin Django": (lambda t, u: _site_admin(u), {"admin_groupe"}),
}


class MatriceDesDroitsTests(JeuUtilisateursMixin, TestCase):
    def test_matrice(self):
        for action, (verifier, autorises) in MATRICE.items():
            for role in ROLES:
                with self.subTest(action=action, role=role):
                    self.assertEqual(verifier(self, getattr(self, role)), role in autorises)

    def test_anonyme_n_a_aucun_droit(self):
        anonyme = AnonymousUser()
        for action, (verifier, _) in MATRICE.items():
            with self.subTest(action=action):
                self.assertFalse(verifier(self, anonyme))
        self.assertFalse(acces.societes_accessibles(anonyme).exists())

    def test_superutilisateur_a_tous_les_droits(self):
        root = type(self.admin_groupe).objects.create_superuser("root", "root@exemple.ci", "x")
        for action, (verifier, _) in MATRICE.items():
            with self.subTest(action=action):
                self.assertTrue(verifier(self, root))

    def test_role_sur(self):
        self.assertEqual(acces.role_sur(self.admin_groupe, self.ooa), "admin_groupe")
        self.assertEqual(acces.role_sur(self.direction, self.ooa), "direction")
        self.assertEqual(acces.role_sur(self.responsable_ooa, self.ooa), "responsable")
        self.assertEqual(acces.role_sur(self.saisie_ooa, self.ooa.pk), "saisie")
        self.assertEqual(acces.role_sur(self.lecture_ooa, self.ooa), "lecture")
        self.assertIsNone(acces.role_sur(self.saisie_anl, self.ooa))
        self.assertIsNone(acces.role_sur(self.inactif, self.ooa))
        self.assertIsNone(acces.role_sur(self.affectation_inactive, self.ooa))

    def test_direction_avec_affectation_de_saisie(self):
        Affectation.objects.create(utilisateur=self.direction, societe=self.anl, role=Affectation.Role.SAISIE)
        acces.vider_cache(self.direction)
        self.assertEqual(acces.role_sur(self.direction, self.anl), "saisie")
        self.assertEqual(acces.role_sur(self.direction, self.ooa), "direction")

    def test_societe_inactive_inaccessible(self):
        Societe.objects.filter(pk=self.ooa.pk).update(actif=False)
        acces.vider_cache(self.saisie_ooa)
        self.assertFalse(acces.peut_lire(self.saisie_ooa, self.ooa))
        self.assertNotIn(self.ooa, acces.societes_accessibles(self.direction))

    def test_role_sur_une_seule_requete(self):
        acces.vider_cache(self.saisie_ooa)
        with self.assertNumQueries(1):
            for _ in range(10):
                acces.role_sur(self.saisie_ooa, self.ooa)
                acces.role_sur(self.saisie_ooa, self.anl)

    @override_settings(SAISIE_FENETRE_MODIFICATION_MOIS=0)
    def test_fenetre_saisie_reglable(self):
        ligne = Ligne(societe=self.ooa, cree_par=self.saisie_ooa, date=mois_decale(1))
        self.assertFalse(acces.peut_modifier_ligne(self.saisie_ooa, ligne))
        ligne.date = mois_decale(0)
        self.assertTrue(acces.peut_modifier_ligne(self.saisie_ooa, ligne))

    def test_fenetre_par_defaut_mois_precedent_inclus(self):
        ligne = Ligne(societe=self.ooa, cree_par=self.saisie_ooa, date=mois_decale(1))
        self.assertTrue(acces.peut_modifier_ligne(self.saisie_ooa, ligne))
        ligne.date = mois_decale(2)
        self.assertFalse(acces.peut_modifier_ligne(self.saisie_ooa, ligne))

    def test_saisie_ne_modifie_pas_une_ligne_supprimee(self):
        self.ligne_saisie_ooa.supprimer()
        self.assertFalse(acces.peut_modifier_ligne(self.saisie_ooa, self.ligne_saisie_ooa))


class QuerysetsFiltresTests(JeuUtilisateursMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Client.objects.create(societe=cls.ooa, nom="PALMCI")
        Client.objects.create(societe=cls.anl, nom="CMA CGM")
        ObjectifMensuel.objects.create(societe=cls.ooa, mois=mois_decale(0), montant=1)

    def test_saisie_anl_ne_voit_aucune_ligne_ooa(self):
        lignes = Ligne.objects.pour_utilisateur(self.saisie_anl)
        self.assertFalse(lignes.filter(societe=self.ooa).exists())
        self.assertEqual(list(lignes), [self.ligne_anl])

    def test_admin_et_direction_voient_tout(self):
        for user in (self.admin_groupe, self.direction):
            self.assertEqual(Ligne.objects.pour_utilisateur(user).count(), 4)
            self.assertEqual(Societe.objects.pour_utilisateur(user).count(), 5)

    def test_societes_clients_objectifs(self):
        self.assertEqual(list(Societe.objects.pour_utilisateur(self.saisie_ooa)), [self.ooa])
        self.assertEqual([c.nom for c in Client.objects.pour_utilisateur(self.saisie_anl)], ["CMA CGM"])
        self.assertFalse(ObjectifMensuel.objects.pour_utilisateur(self.saisie_anl).exists())
        self.assertTrue(ObjectifMensuel.objects.pour_utilisateur(self.lecture_ooa).exists())

    def test_inactifs_ne_voient_rien(self):
        for user in (self.inactif, self.affectation_inactive):
            with self.subTest(user=user.username):
                self.assertFalse(Ligne.objects.pour_utilisateur(user).exists())
                self.assertFalse(Societe.objects.pour_utilisateur(user).exists())
                self.assertFalse(Client.objects.pour_utilisateur(user).exists())


class VueSociete(AccesSocieteMixin, View):
    def get(self, request, *args, **kwargs):
        return HttpResponse(self.societe.code)


class VueSaisie(SaisieSocieteMixin, View):
    def get(self, request, *args, **kwargs):
        return HttpResponse("saisie")


class VueGroupe(VueGroupeMixin, View):
    def get(self, request, *args, **kwargs):
        return HttpResponse("groupe")


class MixinsTests(JeuUtilisateursMixin, TestCase):
    def appeler(self, vue, user, **kwargs):
        requete = RequestFactory().get("/test/")
        requete.user = user
        return vue.as_view()(requete, **kwargs)

    def test_societe_autorisee(self):
        self.assertEqual(self.appeler(VueSociete, self.lecture_ooa, code_societe="ooa").content, b"ooa")

    def test_societe_non_autorisee_renvoie_404(self):
        with self.assertRaises(Http404), self.assertLogs("securite", "WARNING"):
            self.appeler(VueSociete, self.saisie_anl, code_societe="ooa")

    def test_societe_inexistante_renvoie_404(self):
        with self.assertRaises(Http404), self.assertLogs("securite", "WARNING"):
            self.appeler(VueSociete, self.admin_groupe, code_societe="inconnue")

    def test_anonyme_redirige_vers_la_connexion(self):
        reponse = self.appeler(VueSociete, AnonymousUser(), code_societe="ooa")
        self.assertEqual(reponse.status_code, 302)

    def test_saisie(self):
        self.assertEqual(self.appeler(VueSaisie, self.saisie_ooa, code_societe="ooa").status_code, 200)
        with self.assertRaises(PermissionDenied), self.assertLogs("securite", "WARNING"):
            self.appeler(VueSaisie, self.lecture_ooa, code_societe="ooa")
        with self.assertRaises(Http404), self.assertLogs("securite", "WARNING"):
            self.appeler(VueSaisie, self.saisie_anl, code_societe="ooa")

    def test_vue_groupe(self):
        self.assertEqual(self.appeler(VueGroupe, self.direction).status_code, 200)
        with self.assertRaises(Http404), self.assertLogs("securite", "WARNING"):
            self.appeler(VueGroupe, self.responsable_ooa)
        self.assertEqual(self.appeler(VueGroupe, AnonymousUser()).status_code, 302)
