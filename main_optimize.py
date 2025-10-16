# --- PATH SAFETY HEADER ---
from __future__ import annotations
import sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# -----------------------------------------------------------

import argparse
from optimize.grid import ParamGrid, run_grid_search     # adapte aux noms réels
from strategies.turtle_like import TurtleLikeStrategy
from data.store import load_parquet
