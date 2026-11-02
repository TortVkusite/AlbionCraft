"""Run isolated three-process market exchange diagnostics."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.peer_sandbox import run

if __name__=='__main__':run(sys.argv[1] if len(sys.argv)>1 else None)
