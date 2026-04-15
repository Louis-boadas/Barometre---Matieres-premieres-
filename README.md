# 📊 Baromètre Matières Premières — Usine Nouvelle

Script Python d'extraction automatique des indices de matières premières depuis l'API d'Usine Nouvelle, avec stockage dans une base de données SQL Server.

---

## 📋 Table des matières

- [Description](#-description)
- [Architecture](#-architecture)
- [Prérequis](#-prérequis)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Structure SQL](#-structure-de-la-base-de-données)
- [Utilisation](#-utilisation)
- [Renouveler le token JWT](#-renouveler-le-token-jwt)
- [Logs](#-logs)
- [Points d'attention](#-points-dattention)

---

## 📌 Description

Ce projet récupère périodiquement les données d'indices de matières premières publiées sur [Usine Nouvelle](https://www.usinenouvelle.com/indices/) et les insère dans une base SQL Server `barometre`.

**Ce que fait le script :**
- Récupération via l'**API REST** d'Usine Nouvelle (authentification par cookie de session + token Bearer JWT)
- **Parsing JSON** des cours, dates et unités de mesure
- **Insertion et mise à jour** dans SQL Server avec remplissage des jours sans données par propagation de la dernière valeur connue
- Système de **flags** pour distinguer valeurs réelles (`Réelle`) des valeurs interpolées (`Ajouté`)
- **Logs** horodatés dans la console et dans un fichier `barometre.log`

---

## 🏗️ Architecture

```
Usine Nouvelle API
       │
       │  GET /api/indice/{code}
       ▼
  barometre.py
       │
       ├── Lecture table `parametres` (URL + table cible)
       │
       └── Pour chaque indice :
           ├── Appel API → JSON
           ├── Parse valeurs + dates
           ├── DELETE table cible
           ├── INSERT une ligne par jour (squelette temporel)
           ├── UPDATE lignes avec les valeurs réelles
           └── PROPAGATION des valeurs manquantes (flag = "Ajouté")
                        │
                        ▼
                  SQL Server [barometre]
```

---

## ⚙️ Prérequis

| Outil | Version minimale |
|-------|-----------------|
| Python | 3.8+ |
| SQL Server | 2016+ |
| Driver ODBC | `{SQL Server}` installé |
| Abonnement Usine Nouvelle | Actif (nécessaire pour le token JWT) |

---

## 🚀 Installation

```bash
# 1. Cloner le dépôt
git clone https://github.com/<votre-org>/barometre-matieres-premieres.git
cd barometre-matieres-premieres

# 2. Créer un environnement virtuel
python -m venv venv
source venv/bin/activate        # Linux / macOS
venv\Scripts\activate           # Windows

# 3. Installer les dépendances
pip install -r requirements.txt
```

---

## 🔧 Configuration

### 1. Créer le fichier `.env`

Copier le fichier exemple et le remplir :

```bash
cp .env.example .env
```

Renseigner les valeurs dans `.env` :

```env
# SQL Server
SQL_SERVER=<NOM_OU_IP_SERVEUR>
SQL_DATABASE=barometre
SQL_USERNAME=barometre
SQL_PASSWORD=<MOT_DE_PASSE>

# Usine Nouvelle API
UN_BEARER_TOKEN=eyJ0eXAiOiJKV1Qi...
UN_SESSION_COOKIE=0r6e0rgf1i1q735...
```

> ⚠️ **Ne jamais committer le fichier `.env`** — il est listé dans `.gitignore`.

### 2. Préparer la base SQL Server

Exécuter le script de création des tables :

```bash
sqlcmd -S <SERVEUR> -d barometre -U barometre -P <MOT_DE_PASSE> -i sql/init_db.sql
```

---

## 🗄️ Structure de la base de données

### Table `parametres`

| Colonne | Type | Description |
|---------|------|-------------|
| `URL` | VARCHAR(500) | URL de l'API pour chaque indice |
| `TBDD` | VARCHAR(100) | Nom de la table SQL de destination |

### Tables d'indices *(une par indice)*

| Colonne | Type | Description |
|---------|------|-------------|
| `code_indice` | VARCHAR(50) | Code court de l'indice |
| `name` | VARCHAR(255) | Libellé complet |
| `date` | DATETIME | Date de la valeur |
| `valeur` | FLOAT | Valeur de l'indice |
| `unite_de_mesure` | VARCHAR(100) | Ex : `€/tonne`, `$/baril` |
| `flag` | VARCHAR(20) | `Réelle` ou `Ajouté` |

---

## ▶️ Utilisation

```bash
# Lancement simple
python barometre.py

# En tâche planifiée Windows (Planificateur de tâches)
# Commande : python C:\chemin\barometre.py
# Fréquence recommandée : quotidienne (nuit ou matin)
```

---

## 🔑 Renouveler le token JWT

Le token Bearer **expire périodiquement**. Pour le renouveler :

1. Se connecter sur [usinenouvelle.com](https://www.usinenouvelle.com)
2. Ouvrir les DevTools (`F12`) → onglet **Network**
3. Filtrer les requêtes sur `api` ou `indices`
4. Copier le header `Authorization: Bearer <token>` et la valeur du cookie de session
5. Mettre à jour le fichier `.env`

**Vérifier la date d'expiration du token :**

```python
import base64, json
from datetime import datetime

token = "eyJ0eXAi..."  # Votre token
payload = token.split('.')[1]
payload += '=' * (4 - len(payload) % 4)
decoded = json.loads(base64.b64decode(payload))
print("Expire le :", datetime.fromtimestamp(decoded['exp']))
```

---

## 📄 Logs

Le script génère des logs horodatés dans deux endroits :

- **Console** (stdout) — pour le suivi en temps réel
- **`barometre.log`** — historique persistant

Exemple de sortie :

```
2024-03-09 08:00:01 [INFO] === Démarrage du baromètre matières premières ===
2024-03-09 08:00:01 [INFO] 12 indice(s) trouvé(s) dans la table parametres.
2024-03-09 08:00:02 [INFO] Traitement : https://www.usinenouvelle.com/api/...
2024-03-09 08:00:02 [INFO]   → Acier (€/tonne) — 240 valeurs
2024-03-09 08:00:03 [INFO]   ✓ Table 'acier' mise à jour avec succès.
...
2024-03-09 08:00:45 [INFO] === Traitement terminé ===
```

---

## ⚠️ Points d'attention

| Sujet | Détail |
|-------|--------|
| **Sécurité SSL** | `verify=False` est utilisé pour les contraintes réseau internes. À activer en production si possible. |
| **Token JWT** | Expire périodiquement — renouvellement manuel nécessaire (voir section dédiée). |
| **Driver ODBC** | Le driver `{SQL Server}` doit être installé sur la machine d'exécution. |
| **Credentials** | Stockés dans `.env`, jamais dans le code source. |

---

## 📁 Structure du projet

```
.
├── barometre.py        # Script principal
├── requirements.txt    # Dépendances Python
├── .env.example        # Template de configuration
├── .env                # Configuration locale (non versionné)
├── .gitignore          # Fichiers exclus du dépôt
├── sql/
│   └── init_db.sql     # Script de création des tables SQL
└── README.md           # Ce fichier
```

---

## 📝 Licence

Usage interne — projet non destiné à une distribution publique.
