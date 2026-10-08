# Groupe – Suivi des marges (Django)

Application Django monolithique de suivi des marges des sociétés du groupe
(OOA, ANL, OTL, ALON Properties, Mon Livreur Pro) et de la remontée vers Africa Commodities.

**Étape 1 livrée : socle de données, règle de répartition, tests, administration.**

## Installation (développement)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # puis mettre une vraie DJANGO_SECRET_KEY
python manage.py migrate           # crée les 5 sociétés + la règle 25 / 60 / 1-1-1
python manage.py createsuperuser
python manage.py runserver
```

Administration : http://127.0.0.1:8000/gestion-interne/ (URL réglable via `DJANGO_ADMIN_URL`).

Tests : `python manage.py test` (29 tests, validés sur SQLite et PostgreSQL 16).

## Organisation

| App | Rôle |
|---|---|
| `config/` | réglages séparés `base` / `dev` / `prod`, secrets dans `.env` |
| `core/` | mixins communs : horodatage, suppression douce (restaurable) |
| `comptes/` | utilisateur personnalisé (rôles et 2FA à l'étape 2) |
| `societes/` | `Societe` (libellés, champ spécifique, couleurs), `Client`, `ObjectifMensuel` |
| `repartition/` | `RegleRepartition` versionnée + `services.calculer_repartition` |
| `operations/` | `Ligne` (dossier / opération / lot de livraisons) + `selectors` (totaux) |

## Règles métier codées

- **Répartition** : 25 % charges → 60 % du reste à Africa Commodities → solde en 3 parts
  (risques / provision / comptes). Un seul endroit applique la règle : `repartition/services.py`.
- **Arrondi au franc** : chaque part est arrondie ; l'écart éventuel va aux Comptes, donc la
  somme des parts = la marge, toujours (vérifié aussi par une contrainte en base).
- **Répartition figée** : chaque ligne stocke ses 5 montants et la règle utilisée. Une nouvelle
  règle (nouvelle date de début) ne modifie jamais les lignes déjà enregistrées.
- **Objectif mensuel** : valeur du mois, sinon celle du dernier mois renseigné, sinon l'objectif
  par défaut de la société.
- **Clients** : propres à chaque société, sans doublon (majuscules/minuscules ignorées).
- **Contrôles** : quantité > 0, marge > 0, client de la bonne société, Type ALON limité à
  Location / Vente, date couverte par une règle.
- **Suppression douce** des lignes et clients : rien n'est effacé définitivement par erreur.

## Performances

- Montants en `Decimal` (pas de `float`).
- Totaux calculés par la base (`SUM`, `GROUP BY`, `TruncMonth`) : tableau de bord d'une société
  en 2 requêtes, synthèse du groupe en 1 requête + 1 par société.
- Index `(societe, date)` pour les filtres mensuels.

## Étapes suivantes

2. Sécurité : rôles, accès par société, 2FA, anti-bruteforce, CSP, journal d'audit.
3. Interface : saisie HTMX, tableaux de bord, graphiques, confettis.
4. Exports Excel / PDF + import des sauvegardes `.json` du fichier HTML.
5. Déploiement : Docker Compose (Nginx, Gunicorn, PostgreSQL, Redis), HTTPS, sauvegardes.
