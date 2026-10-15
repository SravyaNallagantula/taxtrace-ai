import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["TAXTRACE_DATABASE_URL"] = "postgresql+psycopg://taxtrace:taxtrace@localhost:5434/taxtrace_test"
os.environ["TAXTRACE_PACKET_PATH"] = str(ROOT / "data" / "packet.json")
