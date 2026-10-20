"""Dashboard web do Radar Phishing.

    python -m dashboard            dados reais do banco, em http://127.0.0.1:8765
    python -m dashboard --demo     dados ficticios, para apresentacao e prints
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Rodando como arquivo (python dashboard/__main__.py), a raiz do projeto nao
# esta no caminho de importacao; como modulo (python -m dashboard), ja esta.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402

from dashboard.servidor import criar_app  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m dashboard", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", action="store_true", help="usa dados fictícios")
    parser.add_argument("--porta", type=int, default=8765)
    args = parser.parse_args()
    print(f"Radar Phishing · dashboard em http://127.0.0.1:{args.porta}" + ("  (demonstração)" if args.demo else ""))
    # 127.0.0.1, nunca 0.0.0.0: so este computador acessa.
    uvicorn.run(criar_app(args.demo), host="127.0.0.1", port=args.porta, log_level="warning")


if __name__ == "__main__":
    main()
