# My Pharmacie App

Une application web interactive développée en **Python** avec **NiceGUI** permettant de commander une livraison de médicaments depuis les pharmacies à proximité.

## ✨ Fonctionnalités

- **Catalogue de produit**
- **Barre de recherche**
- **Tri automatique** 
- **Notation et commentaires**
- **Indication des produits nécessitant une ordonnance**
- **Recommandations personalisées**
- **Proposition d'itinéaire optimisé pour les commandes**

## Structure du projet
📦 app  
┣ 📜 main.py — 🚀 Point d’entrée de l’application (lancement du serveur et configuration globale)  
┣ 📜 requirements.txt — 📦 Liste des dépendances Python nécessaires au projet  
┣ 📜 README.md — 📖 Documentation du projet  

┣ 📂 components/ — 🎨 Composants visuels et éléments réutilisables  
┃ ┣ 📜 navbar.py — 🧭 Barre de navigation globale de l'application  
┃ ┗ 📜 theme.py — 🎭 Thème CSS pour améliorer les visuels et l'affichage global  

┣ 📂 routes/ — 🛤️ Pages de l'application (navigation principale)  
┃ ┣ 📜 login.py — 🔑 Page d’authentification ou de création de compte  
┃ ┣ 📜 home.py — 🏠 Page d’accueil avec recherche, tri et affichage produits  
┃ ┣ 📜 profil.py — 👤 Page de gestion du profil de l'utilisateur  
┃ ┣ 📜 details.py — 📄 Page relative à un produit spécifique  
┃ ┣ 📜 map.py — 🗺️ Page de disponibilité d'un produit spécifique  
┃ ┣ 📜 itinerary.py — 🛣️ Page d'affichage et de calcul d'itinéraire  
┃ ┣ 📜 panier.py — 🛒 Page de gestion du panier de commande  
┃ ┣ 📜 wallet.py — 💳 Page de gestion du solde et historique des transactions  
┃ ┣ 📜 order.py — 📦 Page de commande  
┃ ┗ 📜 thanks.py — 🙏 Page de remerciement après une commande  
┣ ┣ 📂 admin/ — 🛠️ Pages et outils de gestion pour les administrateurs  
┃ ┃ ┣ 📜 products.py — 📦 Gestion des produits (ajout, modification, suppression, tags, composants)  
┃ ┃ ┣ 📜 pharmacies.py — 💊 Gestion des pharmacies (ajout, modification, suppression, gestion des stocks)  
┃ ┃ ┣ 📜 users.py — 👥 Gestion des utilisateurs (modification des rôles, wallet, suppression)  
┃ ┃ ┗ 📜 settings.py — ⚙️ Paramètres généraux du site (nom du site, mot de passe admin, statistiques et analytics)   

┣ 📂 services/ — 🛠️ Fonctions utilitaires et logiques métier  
┃ ┣ 📜 auth.py — 🔐 Gestion de l'authentification  
┃ ┣ 📜 file_io.py — 📂 Lecture et chargement des données  
┃ ┣ 📜 items.py — 📦 Fonctions utilitaires sur les objets  
┃ ┣ 📜 distance.py — 📏 Calcul de distances pour le choix d'itinéraire  
┃ ┣ 📜 reviews.py — ⭐ Gestion des notes et commentaires  
┃ ┣ 📜 settings.py —  ⚙️ Fonctions utilitaires pour les paramètres du site   
┃ ┗ 📜 users.py — 👥 Fonctions utilitaires sur les utilisateurs  

┣ 📂 recommendations/ — 🤝 Gestion des recommandations  
┃ ┣ 📜 reco_experiments.ipynb — 📒 Notebook de dev/test pour le moteur de recommandation  
┃ ┣ 📜 recommendations.py — 🤝 Fonctions de recommandation  
┃ ┗ 📜 user_product_matrix.py — 📊 Construit les datasets pour l'entrainement d'un modèle de recommandation  

┣ 📂 security/ — 🛡️ Fonctions utilitaires pour les aspects de sécurité   
┃ ┗ 📜 passwords.py — 🔐 Gestion du hachage des mots de passe  

┣ 📂 static/ — 🎨 Code CSS et JS pour l'application  
┃ ┣ 📜 styles.css — 🎭 Styles CSS globaux  
┃ ┗ 📜 script.js — ⚡ Helper script JS pour le style global

┣ 📂 data/ — 📊 Données brutes et fichiers JSON  
┃ ┣ 📜 create_db.py — 🗄️ Initialise la base de données si elle n'existe pas déjà  
┃ ┣ 📜 backup_db.py — 💾 Crée une copie de la base de données  
┃ ┣ 📜 migrate_json_to_sql.py — 🔄 Script de migration des données JSON vers la base SQLite  
┃ ┣ 📜 migrate_sql_to_json.py — 🔄 Script de migration de la base SQLite vers les fichiers JSON  
┃ ┣ 📜 data.db — 🗃️ Base de données SQLite principale  
┃ ┣ 📜 reviews.json — 💬 Informations sur les commentaires et notations  
┃ ┣ 📜 pharmacies.json — 💊 Informations sur les pharmacies  
┃ ┣ 📜 products.json — 📦 Informations sur les produits  
┃ ┣ 📜 users.json — 👤 Informations utilisateurs  
┃ ┣ 📜 tags.json — 🏷️ Noms et couleurs des tags  
┃ ┣ 📜 settings.json — ⚙️ Paramètres du site  


┗ 📂 images/ — 🖼️ Images d'affichage des produits  


## 📦 Installation

### 1️⃣ Prérequis
- Python 3.13 ou plus
- [pip](https://pip.pypa.io/en/stable/)

### 2️⃣ Installations des dépendances
```bash
pip install -r requirements.txt
```

### 3️⃣ Lancement de l'application
```bash
python -m app.main
```

### 4️⃣ Aller plus loin

- 📘 Consultez le guide [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) pour mettre en place la CI/CD et déployer l'application (Render, Railway, Fly.io, Ionos, etc.).
- 🧪 Ajoutez vos tests (ex. `pytest`) puis complétez le workflow `ci.yml` pour renforcer la qualité.

## 🚀 Déploiement et CI/CD

### Intégration continue

Le dépôt inclut un workflow GitHub Actions (`.github/workflows/ci.yml`) qui s’exécute sur chaque `push` ou `pull request` vers les branches `main` et `work`.

- Installation des dépendances Python (versions 3.11 et 3.12).
- Compilation des modules NiceGUI pour détecter rapidement les erreurs de syntaxe.

Vous pouvez étendre ce workflow en ajoutant des tests automatisés (ex : `pytest`) dès qu’ils seront disponibles.

### Livraison continue (images Docker)

Un second workflow (`.github/workflows/deploy.yml`) construit et publie une image Docker sur le registre GitHub Container Registry (`ghcr.io`) lors :

- d’un déclenchement manuel (`workflow_dispatch`),
- ou de la création d’un tag de version (`vX.Y.Z`).

Les images peuvent ensuite être déployées automatiquement vers votre hébergeur (Render, Railway, Fly.io, Ionos, etc.) via leurs webhooks ou CLIs respectives.

### Variables d’environnement

L’application lit plusieurs variables d’environnement pour faciliter la configuration :

| Variable | Description | Valeur par défaut |
| --- | --- | --- |
| `APP_HOST` | Adresse d’écoute du serveur NiceGUI | `0.0.0.0` |
| `APP_PORT` | Port d’écoute | `8080` |
| `APP_RELOAD` | Recharge automatique (mode dev) | `true` |
| `APP_STORAGE_SECRET` | Secret NiceGUI pour le stockage | `uwu` |

### Exécution via Docker

```bash
# Construction de l’image
docker build -t pharmalink:latest .

# Lancement du conteneur (avec rechargement désactivé)
docker run -p 8080:8080 \
  -e APP_RELOAD=false \
  pharmalink:latest
```

Montez un volume persistant ou migrez vers une base gérée si vous souhaitez conserver la base SQLite entre les déploiements.
