from django.db import IntegrityError, transaction
from django.test import TestCase

from comptes.models import Affectation, Utilisateur
from societes.models import Societe


class AffectationTests(TestCase):
    def setUp(self):
        self.user = Utilisateur.objects.create_user("awa", "awa@exemple.ci", "x")
        self.ooa = Societe.objects.get(code="ooa")

    def test_une_seule_affectation_par_societe(self):
        Affectation.objects.create(utilisateur=self.user, societe=self.ooa, role=Affectation.Role.SAISIE)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Affectation.objects.create(utilisateur=self.user, societe=self.ooa, role=Affectation.Role.LECTURE)

    def test_plusieurs_societes_autorisees(self):
        Affectation.objects.create(utilisateur=self.user, societe=self.ooa, role=Affectation.Role.SAISIE)
        Affectation.objects.create(utilisateur=self.user, societe=Societe.objects.get(code="anl"),
                                   role=Affectation.Role.LECTURE)
        self.assertEqual(self.user.affectations.count(), 2)


class IsStaffSynchroniseTests(TestCase):
    def test_is_staff_suit_le_role_global(self):
        user = Utilisateur.objects.create_user("kofi", "kofi@exemple.ci", "x")
        self.assertFalse(user.is_staff)

        user.role_global = Utilisateur.RoleGlobal.ADMIN_GROUPE
        user.save()
        user.refresh_from_db()
        self.assertTrue(user.is_staff)

        user.role_global = Utilisateur.RoleGlobal.AUCUN
        user.save(update_fields=["role_global"])
        user.refresh_from_db()
        self.assertFalse(user.is_staff)

    def test_is_staff_force_a_faux_sans_role(self):
        user = Utilisateur.objects.create_user("ama", "ama@exemple.ci", "x", is_staff=True)
        self.assertFalse(user.is_staff)

    def test_superutilisateur_reste_staff(self):
        user = Utilisateur.objects.create_superuser("root", "root@exemple.ci", "x")
        self.assertTrue(user.is_staff)
