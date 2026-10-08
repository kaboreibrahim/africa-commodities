from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from comptes.tests.jeu import JeuUtilisateursMixin, mois_decale
from operations import services
from operations.models import Ligne
from societes import services as services_societe
from societes.models import Client, ObjectifMensuel


class ServicesLigneTests(JeuUtilisateursMixin, TestCase):
    def donnees(self, **kw):
        return dict(date=timezone.localdate(), reference="NOUVELLE", quantite=2, marge_unitaire=50_000) | kw

    def test_saisie_cree_une_ligne(self):
        ligne = services.creer_ligne(self.saisie_ooa, self.ooa, **self.donnees())
        self.assertEqual(ligne.cree_par, self.saisie_ooa)
        self.assertEqual(ligne.marge_totale, 100_000)
        self.assertEqual(ligne.part_africa_commodities, 45_000)

    def test_direction_lecture_et_autre_societe_ne_peuvent_rien_creer(self):
        for user in (self.direction, self.lecture_ooa, self.saisie_anl, self.inactif, self.affectation_inactive):
            with self.subTest(user=user.username), self.assertRaises(PermissionDenied), \
                    self.assertLogs("securite", "WARNING"):
                services.creer_ligne(user, self.ooa, **self.donnees())
        self.assertFalse(Ligne.objects.filter(reference="NOUVELLE").exists())

    def test_direction_ne_peut_rien_creer_nulle_part(self):
        for societe in (self.ooa, self.anl):
            with self.subTest(societe=societe.code), self.assertRaises(PermissionDenied), \
                    self.assertLogs("securite", "WARNING"):
                services.creer_ligne(self.direction, societe, **self.donnees())
        with self.assertRaises(PermissionDenied), self.assertLogs("securite", "WARNING"):
            services_societe.ajouter_client(self.direction, self.ooa, "PALMCI")

    def test_donnees_invalides_refusees(self):
        with self.assertRaises(ValidationError) as e:
            services.creer_ligne(self.saisie_ooa, self.ooa, **self.donnees(date=date(1990, 1, 1)))
        self.assertIn("date", e.exception.message_dict)
        client_anl = Client.objects.create(societe=self.anl, nom="CMA CGM")
        with self.assertRaises(ValidationError):
            services.creer_ligne(self.saisie_ooa, self.ooa, **self.donnees(client=client_anl))

    def test_champs_proteges_refuses(self):
        for champ in ("societe_id", "cree_par", "modifie_par", "regle", "marge_totale", "part_charges", "supprime_le"):
            with self.subTest(champ=champ), self.assertRaises(ValueError):
                services.creer_ligne(self.saisie_ooa, self.ooa, **self.donnees(**{champ: None}))
        with self.assertRaises(ValueError):
            services.modifier_ligne(self.admin_groupe, self.ligne_saisie_ooa, societe=self.anl)

    def test_saisie_modifie_sa_ligne_du_mois(self):
        ligne = services.modifier_ligne(self.saisie_ooa, self.ligne_saisie_ooa, quantite=3)
        ligne.refresh_from_db()
        self.assertEqual(ligne.marge_totale, 300_000)
        self.assertEqual(ligne.modifie_par, self.saisie_ooa)
        self.assertEqual(ligne.cree_par, self.saisie_ooa)

    def test_saisie_ne_modifie_ni_la_ligne_d_un_collegue_ni_une_ligne_ancienne(self):
        for ligne in (self.ligne_collegue, self.ligne_ancienne):
            with self.subTest(ligne=ligne.reference), self.assertRaises(PermissionDenied), \
                    self.assertLogs("securite", "WARNING"):
                services.modifier_ligne(self.saisie_ooa, ligne, observation="tentative")
        self.ligne_collegue.refresh_from_db()
        self.assertEqual(self.ligne_collegue.observation, "")

    def test_saisie_ne_sort_pas_une_ligne_de_sa_fenetre(self):
        with self.assertRaises(PermissionDenied), self.assertLogs("securite", "WARNING"):
            services.modifier_ligne(self.saisie_ooa, self.ligne_saisie_ooa, date=mois_decale(3))
        self.assertEqual(Ligne.objects.get(pk=self.ligne_saisie_ooa.pk).date, timezone.localdate())

    def test_responsable_modifie_toutes_les_lignes_de_sa_societe(self):
        services.modifier_ligne(self.responsable_ooa, self.ligne_ancienne, observation="corrigé")
        self.ligne_ancienne.refresh_from_db()
        self.assertEqual(self.ligne_ancienne.observation, "corrigé")
        self.assertEqual(self.ligne_ancienne.modifie_par, self.responsable_ooa)
        with self.assertRaises(PermissionDenied), self.assertLogs("securite", "WARNING"):
            services.modifier_ligne(self.responsable_ooa, self.ligne_anl, observation="x")

    def test_correction_de_libelle_ne_change_pas_la_repartition(self):
        avant = (self.ligne_ancienne.regle_id, self.ligne_ancienne.part_charges)
        services.modifier_ligne(self.admin_groupe, self.ligne_ancienne, observation="libellé")
        self.ligne_ancienne.refresh_from_db()
        self.assertEqual((self.ligne_ancienne.regle_id, self.ligne_ancienne.part_charges), avant)

    def test_suppression_et_restauration(self):
        with self.assertRaises(PermissionDenied), self.assertLogs("securite", "WARNING"):
            services.supprimer_ligne(self.saisie_ooa, self.ligne_saisie_ooa)
        services.supprimer_ligne(self.responsable_ooa, self.ligne_saisie_ooa)
        self.assertFalse(Ligne.objects.filter(pk=self.ligne_saisie_ooa.pk).exists())

        ligne = Ligne.tous.get(pk=self.ligne_saisie_ooa.pk)
        with self.assertRaises(PermissionDenied), self.assertLogs("securite", "WARNING"):
            services.restaurer_ligne(self.lecture_ooa, ligne)
        services.restaurer_ligne(self.admin_groupe, ligne)
        self.assertTrue(Ligne.objects.filter(pk=ligne.pk).exists())


class ServicesSocieteTests(JeuUtilisateursMixin, TestCase):
    def test_responsable_gere_ses_clients(self):
        client = services_societe.ajouter_client(self.responsable_ooa, self.ooa, "  SIFCA   CI ", telephone="0102")
        self.assertEqual(client.nom, "SIFCA CI")
        with self.assertRaises(ValidationError):
            services_societe.ajouter_client(self.responsable_ooa, self.ooa, "sifca ci")
        services_societe.modifier_client(self.responsable_ooa, client, email="contact@sifca.ci")
        services_societe.retirer_client(self.responsable_ooa, client)
        self.assertFalse(Client.objects.exists())
        self.assertEqual(Client.tous.get().email, "contact@sifca.ci")

    def test_saisie_et_autre_societe_ne_gerent_pas_les_clients(self):
        client = Client.objects.create(societe=self.ooa, nom="PALMCI")
        for user in (self.saisie_ooa, self.lecture_ooa, self.direction, self.saisie_anl):
            with self.subTest(user=user.username):
                with self.assertRaises(PermissionDenied), self.assertLogs("securite", "WARNING"):
                    services_societe.ajouter_client(user, self.ooa, "SOGB")
                with self.assertRaises(PermissionDenied), self.assertLogs("securite", "WARNING"):
                    services_societe.retirer_client(user, client)
                with self.assertRaises(PermissionDenied), self.assertLogs("securite", "WARNING"):
                    services_societe.modifier_client(user, client, nom="X")
        with self.assertRaises(ValueError):
            services_societe.ajouter_client(self.responsable_ooa, self.ooa, "X", societe_id=self.anl.pk)

    def test_definir_objectif(self):
        o = services_societe.definir_objectif(self.responsable_ooa, self.ooa, date(2026, 10, 17), 2_000_000)
        self.assertEqual(o.mois, date(2026, 10, 1))
        services_societe.definir_objectif(self.admin_groupe, self.ooa, date(2026, 10, 3), 2_500_000)
        self.assertEqual(ObjectifMensuel.objects.get().montant, 2_500_000)
        with self.assertRaises(ValidationError):
            services_societe.definir_objectif(self.responsable_ooa, self.ooa, date(2026, 11, 1), -5)
        for user in (self.saisie_ooa, self.direction):
            with self.subTest(user=user.username), self.assertRaises(PermissionDenied), \
                    self.assertLogs("securite", "WARNING"):
                services_societe.definir_objectif(user, self.ooa, date(2026, 10, 1), 1)
        with self.assertRaises(PermissionDenied), self.assertLogs("securite", "WARNING"):
            services_societe.supprimer_objectif(self.saisie_ooa, o)
        services_societe.supprimer_objectif(self.responsable_ooa, ObjectifMensuel.objects.get())
        self.assertFalse(ObjectifMensuel.objects.exists())
