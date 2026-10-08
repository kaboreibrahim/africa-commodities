from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from comptes.models import JournalSecurite
from comptes.tests.jeu import JeuUtilisateursMixin
from societes.models import DepenseMensuelle, Societe
from societes.services import definir_depenses


class DepenseMensuelleModeleTests(TestCase):
    def setUp(self):
        self.ooa = Societe.objects.get(code="ooa")

    def test_mois_normalise_au_premier(self):
        depense = DepenseMensuelle.objects.create(societe=self.ooa, mois=date(2026, 10, 17), montant=1_000_000)
        self.assertEqual(depense.mois, date(2026, 10, 1))

    def test_une_seule_saisie_par_mois(self):
        DepenseMensuelle.objects.create(societe=self.ooa, mois=date(2026, 10, 1), montant=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            DepenseMensuelle.objects.create(societe=self.ooa, mois=date(2026, 10, 20), montant=2)

    def test_montant_negatif_refuse(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            DepenseMensuelle.objects.create(societe=self.ooa, mois=date(2026, 10, 1), montant=-1)
        with self.assertRaises(ValidationError):
            DepenseMensuelle(societe=self.ooa, mois=date(2026, 10, 1), montant=-1).full_clean()


class DefinirDepensesTests(JeuUtilisateursMixin, TestCase):
    def test_responsable_saisit_pour_sa_societe(self):
        depense = definir_depenses(self.responsable_ooa, self.ooa, date(2026, 10, 9), 1_200_000, note="loyer + salaires")
        self.assertEqual((depense.mois, depense.montant, depense.saisi_par), (date(2026, 10, 1), 1_200_000,
                                                                               self.responsable_ooa))
        # Mise à jour du même mois (pas de doublon)
        definir_depenses(self.responsable_ooa, self.ooa, date(2026, 10, 1), 1_300_000)
        self.assertEqual(DepenseMensuelle.objects.get().montant, 1_300_000)
        self.assertEqual(DepenseMensuelle.objects.get().history.first().history_user, self.responsable_ooa)

    def test_responsable_ne_saisit_pas_pour_une_autre_societe(self):
        with self.assertRaises(PermissionDenied), self.assertLogs("securite", "WARNING"):
            definir_depenses(self.responsable_ooa, self.anl, date(2026, 10, 1), 1)
        self.assertTrue(JournalSecurite.objects.filter(evenement="acces_refuse",
                                                       details__action="definir_depenses").exists())

    def test_saisie_lecture_direction_refuses(self):
        for user in (self.saisie_ooa, self.lecture_ooa, self.direction, self.inactif):
            with self.subTest(user=user.username), self.assertRaises(PermissionDenied), \
                    self.assertLogs("securite", "WARNING"):
                definir_depenses(user, self.ooa, date(2026, 10, 1), 1)
        self.assertFalse(DepenseMensuelle.objects.exists())

    def test_admin_groupe_saisit_partout(self):
        for societe in Societe.objects.all():
            definir_depenses(self.admin_groupe, societe, date(2026, 10, 1), 500_000)
        self.assertEqual(DepenseMensuelle.objects.count(), 5)

    def test_montant_negatif_refuse_par_le_service(self):
        with self.assertRaises(ValidationError):
            definir_depenses(self.admin_groupe, self.ooa, date(2026, 10, 1), -10)
