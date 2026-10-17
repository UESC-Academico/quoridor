# local_game.py
import argparse

from ui.cli import run_local_cli
from ui.gui import QuoridorGUI

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Partida local de Quoridor")
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Executar no terminal via console (sem interface gráfica)",
    )
    parser.add_argument(
        "--players",
        type=int,
        choices=[2, 4],
        default=2,
        help="Número de jogadores (2 ou 4, padrão: 2)",
    )
    args = parser.parse_args()

    if args.cli:
        run_local_cli(num_players=args.players)
    else:
        app = QuoridorGUI(num_players=args.players)
        app.run()
