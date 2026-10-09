# Groupe – Suivi des marges (Django)

Application Django monolithique de suivi des marges des sociétés du groupe
(OOA, ANL, OTL, ALON Properties, Mon Livreur Pro) et de la remontée vers Africa Commodities.

**Étape 1 livrée : socle de données, règle de répartition, tests, administration.**
**Étape 2 livrée : rôles, accès par société, 2FA, anti-bruteforce, CSP, historique et journal de sécurité.**
**Étape 3 livrée : interface web (saisie HTMX, tableaux de bord, graphiques, Vue Groupe, dépenses et couverture des charges, confettis).**

## Installation (développement)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt   # requirements.txt seul en production
cp .env.example .env               # puis mettre une vraie DJANGO_SECRET_KEY
python manage.py migrate           # crée les 5 sociétés + la règle 25 / 60 / 1-1-1
python manage.py creer_utilisateur --email moi@exemple.ci --nom Nom --prenom Prénom --role-global admin_groupe
python manage.py runserver
```

Connexion : http://127.0.0.1:8000/compte/login/ (par e-mail). Administration :
http://127.0.0.1:8000/gestion-interne/ (URL réglable via `DJANGO_ADMIN_URL`, admin groupe uniquement).

Tests : `python manage.py test` (250 tests, validés sur SQLite et PostgreSQL).

## Organisation

| App | Rôle |
|---|---|
| `config/` | réglages séparés `base` / `dev` / `prod`, secrets dans `.env` |
| `core/` | mixins communs : horodatage, suppression douce (restaurable) |
| `comptes/` | utilisateur, rôles et affectations, **contrôle d'accès (`acces.py`)**, 2FA, journal de sécurité |
| `societes/` | `Societe` (libellés, champ spécifique, couleurs), `Client`, `ObjectifMensuel`, `DepenseMensuelle` |
| `repartition/` | `RegleRepartition` versionnée + `services.calculer_repartition` |
| `operations/` | `Ligne` (dossier / opération / lot de livraisons) + `selectors` (totaux, couverture) + `services` (écritures) |
| `interface/` | écrans web : vues, formulaires, gabarits (`templates/`), JS et CSS (`static/`) |

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

### Objectif et dépenses : deux indicateurs indépendants

| | Objectif mensuel | Dépenses mensuelles |
|---|---|---|
| Nature | une **cible** de marge que la société se fixe | un **constat** : ce qui a réellement été dépensé (loyer, salaires, carburant…) |
| Mois sans saisie | reprend l'objectif du dernier mois renseigné, sinon l'objectif par défaut | **aucun report** : dépenses = 0, statut « dépenses non saisies » |
| Indicateur | progression de la marge vers l'objectif (confettis au franchissement) | **couverture des charges** (simple notification au franchissement) |

**Couverture des charges.** La règle réserve déjà 25 % de la marge aux charges (`part_charges`).
Chaque mois, on compare cette part aux dépenses saisies :

- charges couvertes si part charges ≥ dépenses (et dépenses > 0) ; sinon **reste à couvrir** = dépenses − part ;
- **taux de couverture** = part charges ÷ dépenses × 100 ;
- **marge nécessaire** = dépenses ÷ (pct_charges ÷ 100), avec le pourcentage de la règle en vigueur le 1er du mois.
  Exemple : 1 200 000 F de dépenses → 1 200 000 ÷ 25 % = **4 800 000 F de marge nécessaire** ; avec 2 000 000 F
  de marge, il reste 2 800 000 F à faire, soit ≈ 28 conteneurs à 100 000 F.

Le calcul est fait à un seul endroit : `operations/selectors.py → couverture_charges()`. Les dépenses se saisissent
(Responsable, Admin groupe) dans le tableau de bord de la société ou dans l'admin (« Dépenses mensuelles »).

## Performances

- Montants en `Decimal` (pas de `float`).
- Totaux calculés par la base (`SUM`, `GROUP BY`, `TruncMonth`) : tableau de bord d'une société
  en 2 requêtes, synthèse du groupe en 1 requête + 1 par société.
- Index `(societe, date)` pour les filtres mensuels.

## Sécurité

### Matrice des droits

| Action | Admin groupe | Direction | Responsable (sa société) | Saisie (sa société) | Lecture (sa société) |
|---|:-:|:-:|:-:|:-:|:-:|
| Voir lignes, totaux, tableaux de bord | ✅ toutes | ✅ toutes | ✅ | ✅ | ✅ |
| Voir la vue Groupe consolidée | ✅ | ✅ | ❌ | ❌ | ❌ |
| Ajouter une ligne | ✅ | ❌ | ✅ | ✅ | ❌ |
| Modifier une ligne | ✅ | ❌ | ✅ toutes | ✅ ses lignes, mois en cours et mois précédent | ❌ |
| Supprimer (douce) / restaurer une ligne | ✅ | ❌ | ✅ | ❌ | ❌ |
| Gérer clients et objectifs mensuels | ✅ | ❌ | ✅ | ❌ | ❌ |
| Règle de répartition, sociétés, utilisateurs, affectations | ✅ | ❌ | ❌ | ❌ | ❌ |
| Accès à l'admin Django | ✅ | ❌ | ❌ | ❌ | ❌ |

- Les règles sont appliquées **à un seul endroit** : `comptes/acces.py`. Les services d'écriture
  (`operations/services.py`, `societes/services.py`), les mixins de vues (`comptes/mixins.py`) et
  l'admin s'appuient dessus.
- Hors périmètre : **404** dans les vues (on ne révèle pas l'existence d'une société),
  **`PermissionDenied`** dans les services. Chaque refus est inscrit au journal de sécurité.
- Un compte inactif, une affectation inactive ou une société inactive ne donnent aucun droit.
- Fenêtre de modification du rôle Saisie : `SAISIE_FENETRE_MODIFICATION_MOIS` (1 par défaut).

### Créer un utilisateur

Les comptes sont créés par l'admin groupe : il n'y a pas d'inscription publique.

```bash
python manage.py creer_utilisateur --email awa@exemple.ci --nom Koné --prenom Awa     --societe ooa:responsable --societe anl:lecture
python manage.py creer_utilisateur --email dg@exemple.ci --nom Diallo --prenom Moussa --role-global direction
```

Rôles par société : `responsable`, `saisie`, `lecture`. Rôles groupe : `admin_groupe`, `direction`.
Le mot de passe provisoire est affiché **une seule fois**. Il faut le transmettre par un canal sûr.
Son changement est imposé à la première connexion. On peut aussi créer un compte dans l'admin
(Utilisateurs), puis ajouter ses affectations en bas de la fiche.

### Double authentification (2FA)

- **Obligatoire** pour l'admin groupe et les responsables (`MFA_ROLES_OBLIGATOIRES`) : tant qu'elle
  n'est pas activée, toutes les pages redirigent vers son activation. Elle est facultative pour les autres rôles.
- Activation : *Double authentification* (`/compte/2fa/`). Il faut scanner le QR code avec une application
  (Google Authenticator, Microsoft Authenticator, FreeOTP…), saisir le code, puis **conserver les codes de
  récupération**.
- Téléphone perdu : l'admin groupe supprime l'authentificateur dans l'admin (MFA). Voir `SECURITE.md`.

### Connexion, blocage et sessions

- Connexion par e-mail. Après **5 échecs** pour un même couple e-mail + IP, la connexion est bloquée
  **30 minutes**, même avec le bon mot de passe.
- Débloquer un compte : `python manage.py axes_reset_username <email en minuscules>`
  (ou `axes_reset` pour tout débloquer).
- Les sessions expirent après **2 h d'inactivité** et à la fermeture du navigateur.

### Journal de sécurité et historique

- Admin → **Journal de sécurité** (lecture seule) : connexions, échecs, blocages, 2FA activée ou désactivée,
  mot de passe changé, rôles modifiés, accès refusés, avec la date, l'IP et le navigateur. Les entrées
  sont filtrables par événement, par date et par utilisateur. On n'y enregistre jamais de mot de passe ni de code.
- Purge : `python manage.py purger_journal --jours 365`.
- **Historique** (bouton « Historique » dans l'admin) : chaque modification des lignes, clients, objectifs,
  règles, sociétés, affectations et utilisateurs, avec son auteur. Le mot de passe n'est jamais historisé.
  La restauration d'une ancienne version depuis l'admin est désactivée, car elle contournerait les contrôles.

### En-têtes HTTP

CSP stricte (`'self'` uniquement, sans `unsafe-inline` ni `unsafe-eval`, aucun CDN), `X-Frame-Options: DENY`,
`X-Content-Type-Options`, `Referrer-Policy`, `Cross-Origin-Opener-Policy`, `Permissions-Policy`.
En production, HTTPS est imposé (HSTS) et les cookies sont sécurisés. L'application refuse de démarrer
si la clé secrète est trop courte, si la base est SQLite ou si `ALLOWED_HOSTS` est vide.

### Commandes de contrôle

```bash
pip install -r requirements-dev.txt
pip-audit -r requirements.txt                                   # vulnérabilités connues
bandit -r . -x ./.venv,./*/tests,./*/migrations -ll             # analyse statique
coverage run manage.py test && coverage report                  # tests + couverture
python manage.py check --deploy --settings=config.settings.prod # configuration de production
```

En cas de compte compromis : suivre `SECURITE.md`.

## Interface

Application côté serveur (Django) avec HTMX 2 et Chart.js 4 **hébergés localement** (`static/vendor/`,
versions dans `VERSIONS.txt`). Aucun calcul de répartition en JavaScript : les montants viennent des
sélecteurs et services ; le JavaScript ne fait que dessiner. Tout fonctionne aussi **sans JavaScript**
(formulaires et filtres classiques, avec redirection).

### Écrans et droits

| Route | Écran | Qui y accède |
|---|---|---|
| `/` | redirection : Vue Groupe (Admin, Direction) ou 1re société accessible | tout utilisateur connecté |
| `/s/<code>/` | tableau de bord : indicateurs, objectif, dépenses, 5 graphiques avec tableaux équivalents | lecteurs de la société |
| `/s/<code>/lignes/` | liste filtrée (période, recherche, client, projet), total, pagination ; formulaire d'ajout | lecture : tous ; ajout : Responsable, Saisie, Admin |
| `/s/<code>/lignes/<id>/modifier/` | modification (boîte de dialogue) | Admin, Responsable ; Saisie : ses lignes du mois et du mois précédent |
| `…/supprimer/`, `…/restaurer/`, `/s/<code>/corbeille/` | suppression douce (avec « Annuler »), corbeille | Responsable, Admin |
| `/s/<code>/clients/` | clients avec leur nombre de lignes | lecture : tous ; gestion : Responsable, Admin |
| `/s/<code>/objectif/`, `/s/<code>/depenses/` | objectif et dépenses du mois (HTMX) | Responsable, Admin |
| `/groupe/` | Vue Groupe consolidée | Admin groupe, Direction |
| `/regle/` | règle en vigueur, exemples chiffrés, historique | tous (lecture) |
| `/theme/<code>.css` | couleurs de la société (feuille générée, cache 1 h) | lecteurs de la société |

Une société non autorisée renvoie une **404** ; une action non permise sur une société lisible, une **403**.
Les boutons non autorisés ne sont pas affichés, et le serveur revérifie toujours.

### Sélecteur de mois

Le mois de suivi passe dans l'adresse (`?mois=2026-10`) et reste mémorisé en session ; par défaut, le mois
courant. Une valeur invalide donne le mois courant. Boutons ‹ › et champ mois dans l'en-tête.

### Confettis et notifications

Quand un enregistrement **fait passer** la société au-dessus de son objectif du mois, le serveur envoie
l'évènement HTMX `objectifAtteint` (sans JavaScript : un message Django étiqueté `objectif`) : confettis aux
couleurs de la société (≈ 4,5 s), toast, bandeau et ✔ dans l'onglet. Une seule fois par franchissement :
modifier une observation ne relance rien ; supprimer puis rajouter la ligne relance. Si le navigateur demande
de réduire les animations (`prefers-reduced-motion`), pas de confettis, seulement le toast et le bandeau.
Le passage à « charges couvertes » envoie `chargesCouvertes` : simple toast, sans confettis.

### Ajouter une société

1. Admin → **Sociétés** → Ajouter : code (court, en minuscules, ex. `otl`), nom, ordre, libellés de l'activité
   (référence, quantité, marge, unité) et, si besoin, le champ spécifique (texte ou liste de choix).
2. **Charte graphique** : couleur principale, foncée, accent et couleur de série (graphiques du groupe), au format
   `#RRGGBB`. Choisir une couleur principale assez foncée : le texte des boutons est blanc.
3. **Logo** : PNG, JPEG ou WEBP, 2 Mo maximum. Sans logo téléversé, l'application cherche
   `static/img/logos/<code>.png|jpg|webp`, sinon affiche un badge avec le code.
4. Donner les accès : affectations (Responsable, Saisie, Lecture) en bas de la fiche société.

## Étapes suivantes

4. Exports Excel / PDF + import des sauvegardes `.json` du fichier HTML.
5. Déploiement : Docker Compose (Nginx, Gunicorn, PostgreSQL, Redis), HTTPS, sauvegardes.
