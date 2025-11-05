# Guide de déploiement et d'exploitation

Ce document complète les workflows GitHub Actions fournis dans ce dépôt et décrit, étape par étape, comment mettre en place l'intégration continue (CI), la livraison continue (CD) et le déploiement sur différents hébergeurs.

## 1. Pré-requis

- Un dépôt GitHub (privé ou public) contenant ce projet.
- Un compte sur GitHub Packages pour stocker les images Docker (inclus avec GitHub).
- Facultatif : un compte sur votre fournisseur d'hébergement (Render, Railway, Fly.io, Ionos, etc.).

## 2. Préparer GitHub Actions

1. **Activer GitHub Actions** dans l'onglet `Actions` de votre dépôt.
2. Vérifier que les workflows sont présents :
   - `.github/workflows/ci.yml` — vérifie les dépendances et compile le code sur chaque `push` ou `pull request`.
   - `.github/workflows/deploy.yml` — construit et pousse l'image Docker sur GitHub Container Registry (GHCR).
3. **Configurer les permissions** dans `Settings > Actions > General` :
   - Autoriser les workflows à créer et publier des packages (`Read and write permissions`).
4. (Optionnel) Créer un *Environment* `production` dans `Settings > Environments` pour exiger une validation manuelle avant déploiement.

## 3. Tester la CI localement

Avant de pousser, vérifiez que l'application se lance :

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

Pour simuler la CI :

```bash
python -m compileall app
```

## 4. Publier une image Docker vers GHCR

1. Ouvrez `Settings > Packages` et assurez-vous que le registre GHCR est activé.
2. Dans `Settings > Secrets and variables > Actions`, créez si besoin les secrets suivants :
   - `GHCR_USERNAME` (facultatif, `github.actor` est utilisé par défaut).
   - `GHCR_TOKEN` si vous souhaitez utiliser un PAT (sinon `GITHUB_TOKEN` suffit).
3. Pour déclencher le workflow `Deploy` :
   - Depuis l'onglet `Actions`, sélectionnez `Deploy` puis `Run workflow`.
   - Ou créez un tag de version `vX.Y.Z` : `git tag v1.0.0 && git push origin v1.0.0`.
4. Le workflow construit l'image et la publie sous `ghcr.io/<organisation>/<répo>:<tag>`.

## 5. Déployer selon l'hébergeur

### Render

1. Créez un **Web Service** et connectez-le à votre dépôt GitHub.
2. Dans l'onglet `Settings`, activez le déploiement via image Docker (`Deploy Docker Image from Registry`).
3. Renseignez l'image publiée par GHCR (ex. `ghcr.io/mon-org/pharmalink:latest`).
4. Ajoutez les variables d'environnement (`APP_HOST`, `APP_PORT`, `APP_RELOAD`, `APP_STORAGE_SECRET`).
5. Configurez la commande de lancement : `python -m app.main`.

### Railway

1. Créez un nouveau projet Railway et choisissez `Deploy from GitHub Repo`.
2. Sélectionnez votre dépôt et laissez Railway construire l'image.
3. Si vous préférez utiliser GHCR : ajoutez un service `Deploy Docker Image` avec l'URL GHCR.
4. Définissez les variables d'environnement et le port `8080` exposé.

### Fly.io

1. Installez la CLI : `curl -L https://fly.io/install.sh | sh`.
2. Connectez-vous : `fly auth login`.
3. Initialisez l'app : `fly launch` (choisissez Dockerfile existant).
4. Mettez à jour `fly.toml` pour exposer le port 8080 et définir les variables d'environnement.
5. Déployez : `fly deploy --build-only` (optionnel) puis `fly deploy`.

### Ionos (Compute Engine ou Managed Kubernetes)

- **Compute Engine (VM)** :
  1. Créez une VM Ubuntu.
  2. Installez Docker (`apt install docker.io`).
  3. Connectez-vous à GHCR : `echo $CR_PAT | docker login ghcr.io -u <user> --password-stdin`.
  4. Téléchargez et exécutez l'image :
     ```bash
     docker pull ghcr.io/mon-org/pharmalink:latest
     docker run -d --name pharmalink -p 80:8080 \
       -e APP_RELOAD=false \
       -e APP_STORAGE_SECRET=<secret> \
       ghcr.io/mon-org/pharmalink:latest
     ```
  5. Configurez un service systemd ou Docker Compose pour un démarrage automatique.

- **Managed Kubernetes** :
  1. Poussez l'image sur GHCR (via le workflow `Deploy`).
  2. Créez un fichier `deployment.yaml` pointant vers l'image GHCR et exposant le port 8080.
  3. Appliquez la configuration : `kubectl apply -f deployment.yaml`.
  4. Configurez un `Service` de type `LoadBalancer` ou `Ingress` selon vos besoins.

## 6. Gestion de la base de données

- Par défaut, l'application utilise `data/data.db` (SQLite). Ce fichier n'est pas persistant dans un conteneur stateless.
- Solutions :
  - Monter un volume (`docker run -v /srv/pharmalink/data:/app/data ...`).
  - Migrer vers une base managée (PostgreSQL, MySQL) en adaptant le code NiceGUI.
  - Sauvegarder régulièrement la base avec `app/data/backup_db.py`.

## 7. Aller plus loin

- Ajouter des tests `pytest` et les intégrer à `ci.yml`.
- Mettre en place un scan de sécurité (`pip-audit`, `bandit`).
- Ajouter un déploiement automatique vers un environnement de *staging* avant la production.

Ce guide répond aux questions les plus fréquentes après la mise en place des workflows CI/CD et vous aide à choisir et configurer un hébergeur adapté.
