# api_tests/test_oanda_connection.py
# -*- coding: utf-8 -*-
"""
Test de connectivité et de permissions API OANDA.
Ce script :
- charge les variables d'environnement depuis .env
- initialise le client OANDA
- ping le compte (solde, NAV, marge)
- liste 5 instruments disponibles
- télécharge quelques chandeliers récents (facultatif, pour test data)

À exécuter depuis la racine du projet :
    python api_tests/test_oanda_connection.py
"""

import os
from datetime import datetime, timedelta
import pandas as pd
from dotenv import load_dotenv

# Importer le client OANDA (assure-toi que le PYTHONPATH contient le root du projet)
from data.datasource_oanda import OandaClient, OandaConfig

# Charger le fichier .env
load_dotenv()

def main():
    print("=" * 60)
    print("🔗 Test de connexion OANDA")
    print("=" * 60)

    # Lecture des variables d'environnement
    api_token = os.getenv("OANDA_API_TOKEN")
    account_id = os.getenv("OANDA_ACCOUNT_ID")
    env = os.getenv("OANDA_ENV", "practice")

    if not api_token or not account_id:
        print("❌ Variables d'environnement manquantes. Vérifie ton fichier .env")
        print("   Requis : OANDA_API_TOKEN, OANDA_ACCOUNT_ID, OANDA_ENV")
        return

    print(f"Environnement : {env}")
    print(f"Compte : {account_id}")

    # Initialiser la configuration
    cfg = OandaConfig(API_TOKEN=api_token, ACCOUNT_ID=account_id, ENV=env)

    # Créer le client
    client = OandaClient(cfg)

    # 1️⃣ Ping compte
    print("\n📡 Vérification du compte...")
    try:
        summary = client.ping_account()
        balance = summary["account"]["balance"]
        nav = summary["account"]["NAV"]
        currency = summary["account"]["currency"]
        print(f"✅ Connexion réussie. Solde: {balance} {currency}, NAV: {nav}")
    except Exception as e:
        print(f"❌ Erreur lors du ping du compte : {e}")
        return

    # 2️⃣ Liste des instruments
    print("\n📜 Liste de quelques instruments tradables :")
    try:
        instruments = client.list_instruments()
        for i, inst in enumerate(instruments[:5]):
            print(f"  {i+1}. {inst['name']} — {inst['type']} ({inst['displayName']})")
    except Exception as e:
        print(f"⚠️ Impossible de récupérer la liste des instruments : {e}")

    # 3️⃣ Téléchargement de test (facultatif)
    print("\n🕒 Téléchargement de test (XAU_USD, 1 jour de données en H1)...")
    try:
        end = datetime.utcnow()
        start = end - timedelta(days=1)
        df = client.fetch_ohlc(symbol="XAU_USD", timeframe="H1", start=start, end=end)
        if len(df) == 0:
            print("⚠️ Aucun chandelier renvoyé.")
        else:
            print(f"✅ {len(df)} chandeliers téléchargés :")
            print(df.tail(3))
    except Exception as e:
        print(f"⚠️ Échec du téléchargement des chandeliers : {e}")

    print("\n✅ Test terminé avec succès (si aucune erreur critique ci-dessus).")


if __name__ == "__main__":
    main()
# Fin du script
# =====================================================