from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from societes.models import Client, ObjectifMensuel, Societe


class SocietesInitialesTests(TestCase):
    def test_cinq_societes_creees(self):
        self.assertEqual(list(Societe.objects.values_list("code", flat=True)), ["ooa", "anl", "otl", "alon", "mlp"])

    def test_champs_specifiques(self):
        self.assertEqual(Societe.objects.get(code="alon").choix_extra, ["Location", "Vente"])
        self.assertEqual(Societe.objects.get(code="mlp").champ_extra_libelle, "Zone")
        self.assertEqual(Societe.objects.get(code="mlp").marge_defaut, 1000)


class ObjectifTests(TestCase):
    def setUp(self):
        self.ooa = Societe.objects.get(code="ooa")

    def test_objectif_par_defaut(self):
        self.assertEqual(self.ooa.objectif_pour(date(2026, 10, 15)), 1_000_000)

    def test_objectif_du_mois_puis_report_sur_les_mois_suivants(self):
        ObjectifMensuel.objects.create(societe=self.ooa, mois=date(2026, 9, 20), montant=1_200_000)
        self.assertEqual(ObjectifMensuel.objects.get().mois, date(2026, 9, 1))  # normalisé au 1er
        self.assertEqual(self.ooa.objectif_pour(date(2026, 9, 1)), 1_200_000)
        self.assertEqual(self.ooa.objectif_pour(date(2026, 11, 3)), 1_200_000)  # repris du dernier mois saisi
        self.assertEqual(self.ooa.objectif_pour(date(2026, 8, 1)), 1_000_000)   # avant : défaut

    def test_un_seul_objectif_par_mois(self):
        ObjectifMensuel.objects.create(societe=self.ooa, mois=date(2026, 10, 1), montant=1)
        with self.assertRaises(IntegrityError):
            ObjectifMensuel.objects.create(societe=self.ooa, mois=date(2026, 10, 5), montant=2)


class ClientTests(TestCase):
    def setUp(self):
        self.ooa = Societe.objects.get(code="ooa")
        self.anl = Societe.objects.get(code="anl")

    def test_doublon_insensible_a_la_casse_refuse(self):
        Client.objects.create(societe=self.ooa, nom="PALMCI")
        with self.assertRaises(ValidationError):
            Client(societe=self.ooa, nom="palmci").validate_constraints()

    def test_meme_client_autorise_dans_deux_societes(self):
        Client.objects.create(societe=self.ooa, nom="PALMCI")
        Client.objects.create(societe=self.anl, nom="PALMCI")
        self.assertEqual(Client.objects.count(), 2)

    def test_client_supprime_peut_etre_recree(self):
        c = Client.objects.create(societe=self.ooa, nom="SOGB")
        c.supprimer()
        Client.objects.create(societe=self.ooa, nom="SOGB")
        self.assertEqual(Client.objects.count(), 1)
        self.assertEqual(Client.tous.count(), 2)

    def test_espaces_nettoyes(self):
        self.assertEqual(Client.objects.create(societe=self.ooa, nom="  SIFCA   CI ").nom, "SIFCA CI")
