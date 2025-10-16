# 🐢 Turtle-Like Trading Framework

> Framework Python modulaire inspiré des principes de **Richard Dennis & des Turtle Traders**, conçu pour l’expérimentation, le backtesting et le développement de stratégies systématiques (Breakouts, Donchian, ATR, etc.) sur données OANDA ou autres brokers.

---

## 🚀 Objectifs du projet

Ce projet vise à fournir une **architecture propre et extensible** pour :
- Télécharger et stocker les données de marché (OANDA, CSV, Parquet, etc.)
- Agréger les timeframes et vérifier la cohérence des données
- Calculer des indicateurs techniques (ATR, Donchian, Moyennes mobiles, etc.)
- Implémenter des stratégies de trading modulaires (ex. Turtle-like)
- Permettre des backtests, de la simulation et, potentiellement, une exécution en conditions réelles (*à vos risques et périls*).

---

## 🧱 Structure du projet

```bash
project_root/
│
├─ config/
│  ├─ config.py                 # Variables globales (risque, levier, paramètres par défaut)
│  └─ univers.py                # Listes d’actifs par “profils” (FX_majors, Metals, Indices, Crypto…)
│
├─ data/
│  ├─ datasource_oanda.py       # Connexion à OANDA (live & historique)
│  ├─ downloader.py             # Téléchargement & mise à jour locale (par symbole/timeframe)
│  ├─ store.py                  # Lecture/écriture des fichiers (parquet/csv), validations
│  └─ resampling.py             # Agrégation M1→M5→M15→H1→H4→D1
│
├─ indicators/
│  ├─ atr.py                    # Average True Range
│  ├─ donchian.py               # Canaux de Donchian (Breakouts)
│  └─ ma.py                     # Moyennes mobiles (SMA/EMA/WMA…)
│
├─ strategies/
│  └─ turtle_like.py            # Stratégie principale (Breakout + ATR Stop)
│
├─ tests/
│  ├─ test_data_integrity.py
│  └─ test_indicators.py
│
└─ main.py                      # Point d’entrée du projet
```

---

## ⚙️ Installation

```bash
git clone https://github.com/<ton-username>/<ton-repo>.git
cd <ton-repo>
python -m venv .venv
source .venv/bin/activate   # ou .venv\Scripts\activate sous Windows
pip install -r requirements.txt
```

---

## 🔑 Configuration

### 🔧 Fichier d'environnement (`.env`)

Le projet utilise un fichier **`.env`** pour stocker les variables sensibles (clé API OANDA, identifiant de compte, etc.).  
Ce fichier **n’est pas versionné** pour des raisons de sécurité (il est listé dans `.gitignore`).  

Un modèle est fourni sous le nom **`env.example`** — copiez-le et remplissez vos propres valeurs :

```bash
cp env.example .env
```

Ensuite, éditez le fichier `.env` avec vos informations :
```bash
OANDA_API_KEY=ta_clé_personnelle
OANDA_ACCOUNT_ID=ton_numéro_de_compte
OANDA_ENV=practice
```

⚠️ **Ne jamais pousser** le fichier `.env` sur GitHub.  
Il contient des informations confidentielles et spécifiques à ton environnement local.

---

## ⚠️ Avertissement & Responsabilité

> **Ce projet est fourni à titre éducatif et expérimental.**
> Il **ne constitue en aucun cas un conseil en investissement.**
>  
> L’auteur **décline toute responsabilité** pour toute perte financière, directe ou indirecte, liée à l’utilisation du code, en particulier dans un **environnement de trading réel (live trading)**.  
> L’utilisation du code se fait **à vos propres risques**.  
>  
> Lisez le fichier [`DISCLAIMER.md`](DISCLAIMER.md) pour les conditions détaillées.

---

## 📜 Licence

Le code source est distribué sous **Licence MIT + Commons Clause** :
- ✅ Usage personnel, éducatif et interne autorisé  
- ❌ Revente, redistribution commerciale ou intégration dans un produit payant **interdite**  
- ⚠️ Sans aucune garantie, explicite ou implicite

Consultez le fichier [`LICENSE`](LICENSE) pour le texte complet.

---

## 🧑‍💻 Auteur

**Christophe Fauchère (alias Genysix)**  
Chef de projet informatique passionné par le trading algorithmique, la data et la performance.

---
