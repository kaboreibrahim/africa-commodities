# Procédure en cas de compte compromis

À appliquer dès qu'un compte est suspect : mot de passe divulgué, téléphone 2FA perdu ou volé,
connexions inhabituelles dans le journal. Les étapes sont faites par l'admin groupe, dans l'ordre.

## 1. Désactiver le compte

Admin → **Utilisateurs** → décocher « Actif » → Enregistrer.

L'utilisateur ne peut plus se connecter. Toutes les vérifications de droits le refusent, même s'il
a encore une session ouverte (`comptes/acces.py` exige `is_active`).

## 2. Forcer la déconnexion (supprimer ses sessions)

```bash
python manage.py shell -c "
from django.contrib.sessions.models import Session
from comptes.models import Utilisateur
u = Utilisateur.objects.get(email='personne@exemple.ci')
n = [s.delete() for s in Session.objects.all() if s.get_decoded().get('_auth_user_id') == str(u.pk)]
print(len(n), 'session(s) supprimée(s)')
"
```

## 3. Réinitialiser sa double authentification

Admin → **MFA / Authenticators** : supprimer les authentificateurs de cet utilisateur (TOTP et codes
de récupération). La suppression est inscrite au journal (« 2FA désactivée »). À sa prochaine connexion,
si son rôle l'exige (admin groupe, responsable), il devra activer une nouvelle 2FA.

Donner ensuite un **nouveau mot de passe provisoire** : Admin → Utilisateurs → « Mot de passe » →
cocher « doit changer son mot de passe ». Transmettre le mot de passe par un canal sûr, distinct de l'e-mail.

## 4. Lire le journal et l'historique

- Admin → **Journal de sécurité** : filtrer sur l'utilisateur. Vérifier les connexions (date, IP,
  navigateur), les échecs, les blocages, les accès refusés et les changements de rôle.
- Admin → Lignes / Clients / Objectifs → **Historique** : repérer les modifications faites par ce compte
  (colonne « utilisateur »). Corriger les données en passant par l'admin (et non par la restauration
  d'une version, désactivée volontairement).
- Débloquer si nécessaire : `python manage.py axes_reset_username personne@exemple.ci`.

## 5. Changer `DJANGO_SECRET_KEY` si nécessaire

À faire si la clé a pu fuiter (fichier `.env` exposé, serveur compromis) :

1. Générer une nouvelle clé (au moins 50 caractères) :
   `python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"`.
2. La remplacer dans `.env` et redémarrer l'application.

**Attention :** cela invalide **toutes** les sessions (tout le monde est déconnecté) ainsi que les liens
de réinitialisation de mot de passe en cours. Prévenir les utilisateurs avant.

Si c'est la **base de données** qui a fuité (et pas seulement la clé) : les secrets TOTP y sont stockés
en clair (comportement par défaut d'allauth). Il faut alors supprimer tous les authentificateurs
(admin → MFA) et faire réactiver la 2FA à tout le monde.

Après l'incident, réactiver le compte seulement une fois la cause comprise, et le noter dans le journal
d'exploitation.
