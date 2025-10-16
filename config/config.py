# config/config.py
from dotenv import load_dotenv
import os

# Charge les variables depuis .env (si présent)
load_dotenv()

# Exemple d’accès :
OANDA_TOKEN = os.getenv("OANDA_API_TOKEN")
OANDA_ACCOUNT = os.getenv("OANDA_ACCOUNT_ID")
OANDA_ENV = os.getenv("OANDA_ENV", "practice")

DATA_ROOT = os.getenv("DATA_ROOT", "data_local")
# Fin de config/config.py