# Déploiement sur cPanel (MySQL + Git)

Application Django 5.2 : il faut **Python 3.10 ou plus** (cPanel → *Setup Python App*) et **MySQL 8.0.16+ ou MariaDB 10.5+**.

## 1. Mettre le projet sur Git (poste local)

Le dépôt doit être **privé** (GitHub, GitLab, Bitbucket…).

```bash
git remote add origin https://github.com/VOTRE-COMPTE/groupe-marges.git
git push -u origin master          # la branche s'appelle « master » dans ce projet
```

Les secrets ne partent **jamais** dans Git : `.env`, `.env.*` et les bases SQLite sont dans `.gitignore`
(sauf `.env.example`, qui ne contient que des exemples). Vérifier avant le premier envoi :

```bash
git status --short            # aucun fichier .env ne doit apparaître
git ls-files | grep -i env    # doit afficher seulement .env.example
```

## 2. Créer la base MySQL (cPanel → *MySQL® Databases*)

Base `c2508341c_africa_commodities`, utilisateur `c2508341c_africa_commodities`, puis **« Add User To Database »**
avec **ALL PRIVILEGES**. Sans cette étape, la connexion est refusée.

> MySQL n'est accessible que depuis le serveur (`localhost`). Les migrations se lancent donc **sur le serveur** (étape 5),
> pas depuis votre PC. En local, gardez SQLite ou PostgreSQL.

## 3. Récupérer le code sur le serveur (cPanel → *Git™ Version Control* → *Create*)

- *Clone URL* : l'adresse du dépôt (dépôt privé : ajouter la clé SSH publique fournie par cPanel comme *deploy key*).
- *Repository Path* : `/home/c2508341c/groupe_marges` (**hors** de `public_html`).

## 4. Créer l'application Python (cPanel → *Setup Python App* → *Create Application*)

| Champ | Valeur |
|---|---|
| Python version | 3.11 ou 3.12 |
| Application root | `groupe_marges` |
| Application URL | votre domaine (ou sous-domaine) |
| Application startup file | `passenger_wsgi.py` |
| Application Entry point | `application` |

Puis, dans la fenêtre du terminal cPanel (la commande exacte *« Enter to the virtual environment »* est affichée sur la page) :

```bash
source /home/c2508341c/virtualenv/groupe_marges/3.11/bin/activate && cd /home/c2508341c/groupe_marges
pip install -r requirements.txt
```

Si `psycopg[binary]` ne s'installe pas (inutile avec MySQL), supprimer cette ligne de `requirements.txt` sur le serveur.

## 5. Configuration (fichier `.env` sur le serveur)

Dans le *Gestionnaire de fichiers*, créer `/home/c2508341c/groupe_marges/.env` (permissions `600`) à partir de
`.env.cpanel` (fichier préparé sur votre PC, **non versionné**). À adapter :

- `DJANGO_ALLOWED_HOSTS` et `DJANGO_CSRF_TRUSTED_ORIGINS` : votre vrai nom de domaine (HTTPS) ;
- `DJANGO_SECRET_KEY` : déjà générée (ne la changez que si nécessaire : cela déconnecte tout le monde) ;
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST=localhost` ;
- `DJANGO_NB_PROXYS_DE_CONFIANCE=0` tant que l'hébergeur n'ajoute pas lui-même `X-Forwarded-For` (sinon l'adresse IP,
  utilisée par le blocage des tentatives de connexion, pourrait être falsifiée) ;
- `DJANGO_HSTS_SECONDS=300` au premier déploiement, puis `31536000` quand le HTTPS fonctionne partout.

Activer le HTTPS : cPanel → *SSL/TLS Status* → *Run AutoSSL*.

## 6. Initialiser (terminal cPanel, environnement virtuel activé)

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
python manage.py creer_utilisateur --email admin@votre-domaine.ci --nom NOM --prenom Prenom --role-global admin_groupe
```

Le mot de passe provisoire s'affiche **une seule fois**. À la première connexion : changement du mot de passe puis
activation de la 2FA (obligatoire pour l'administrateur). Redémarrer l'application : bouton *Restart* de *Setup Python App*
(ou `touch /home/c2508341c/groupe_marges/tmp/restart.txt`).

Fichiers statiques : servis par WhiteNoise (rien à configurer dans Apache). Logos téléversés des sociétés : créer le dossier
`/home/c2508341c/public_html/media` (déjà prévu dans `DJANGO_MEDIA_ROOT`) ; Apache le sert directement.

## 7. Mettre à jour après un changement

Sur votre PC : `git push`. Sur le serveur (*Git Version Control* → *Update from Remote*, ou terminal) :

```bash
cd /home/c2508341c/groupe_marges && git pull
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
touch tmp/restart.txt
```

## 8. Tâches planifiées (cPanel → *Cron Jobs*)

```
15 2 * * *  /home/c2508341c/virtualenv/groupe_marges/3.11/bin/python /home/c2508341c/groupe_marges/manage.py expirer_habilitations
30 2 * * 0  /home/c2508341c/virtualenv/groupe_marges/3.11/bin/python /home/c2508341c/groupe_marges/manage.py purger_journal
```

## 9. Points d'attention MySQL

- **Tests** : la suite de tests a été exécutée sur PostgreSQL et SQLite, **pas sur MySQL**. Après le premier déploiement,
  parcourir l'application (connexion + 2FA, saisie d'un dossier, Vue Groupe, habilitations, PDF).
- **Contrainte « un client unique par société »** : cette règle est une contrainte *partielle* (clients non supprimés).
  MySQL ne sait pas créer de contrainte partielle : Django ne la crée pas en base, mais la vérifie dans l'application
  (`full_clean` dans les services). Aucun contournement par l'interface.
- **Sauvegardes** : cPanel → *Backup* ou `mysqldump` (planifié en cron), à conserver hors du serveur.
- **Mot de passe de la base** : il a été communiqué hors du serveur ; le changer (cPanel → *MySQL Databases* → *Change Password*)
  puis mettre à jour `DB_PASSWORD` dans le `.env` du serveur.
