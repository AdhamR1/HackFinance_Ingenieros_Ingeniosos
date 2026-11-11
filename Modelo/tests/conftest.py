# Puts Modelo/src on sys.path: the pipeline scripts import each other as plain modules.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
