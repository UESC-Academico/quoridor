import argparse
import sys
import time
from network.config import DEFAULT_NS_HOST, DEFAULT_NS_PORT, DEFAULT_SERVER_NAME, logger
from network.client import QuoridorClient


def run_cli_loop(client: QuoridorClient) -> None:
    """Modo texto interativo no terminal para testes e partidas sem interface gráfica."""
    print("=" * 60)
    print(f"Conectado como {client.player_name} (ID: {client.player_id})")
    print("Comandos disponíveis:")
    print("  start             - Inicia a partida (se houver 2 ou 4 jogadores)")
    print("  move <r> <c>      - Move o peão para a linha r e coluna c (0 a 8)")
    print("  wall <r> <c> <H|V>- Coloca uma parede na posição (r, c) com orientação H ou V")
    print("  moves             - Mostra movimentos válidos atuais")
    print("  state             - Exibe estado atual da partida")
    print("  quit              - Sair do jogo")
    print("=" * 60)

    def print_event(ev_type: str, data: dict) -> None:
        if ev_type == "state_changed":
            msg = data.get("message", "")
            turn = data.get("state", {}).get("turn")
            print(f"\n[EVENTO] {msg} (Vez do Jogador {turn})")
        elif ev_type == "game_started":
            print("\n[EVENTO] A partida foi iniciada!")
        elif ev_type == "game_over":
            print(f"\n[EVENTO] Partida encerrada! Vencedor: {data.get('winner_name')}")

    client.add_listener(print_event)

    while True:
        try:
            cmd = input(f"[{client.player_name}] > ").strip()
            if not cmd:
                continue

            parts = cmd.split()
            op = parts[0].lower()

            if op in ("quit", "exit"):
                break
            elif op == "start":
                ok, msg = client.start_game()
                print(f"Resultado: {msg}")
            elif op == "moves":
                moves = client.get_valid_moves()
                print(f"Movimentos válidos: {moves}")
            elif op == "state":
                state = client.get_game_state()
                print(f"Turno: {state.get('turn')}, Vencedor: {state.get('winner')}")
                for pid, p in state.get("players", {}).items():
                    print(f"  P{pid} ({p['name']}): pos={p['position']}, paredes={p['remaining_walls']}")
            elif op == "move" and len(parts) == 3:
                r, c = int(parts[1]), int(parts[2])
                ok, msg = client.move_player((r, c))
                print(f"Resultado: {msg}")
            elif op == "wall" and len(parts) == 4:
                r, c = int(parts[1]), int(parts[2])
                orientation = parts[3].upper()
                ok, msg = client.place_wall((r, c), orientation)
                print(f"Resultado: {msg}")
            else:
                print("Comando inválido. Digite 'start', 'moves', 'move <r> <c>', 'wall <r> <c> <H|V>', ou 'quit'.")
        except KeyboardInterrupt:
            break
        except Exception as exc:
            print(f"Erro: {exc}")

    client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="Cliente Pyro5 para Quoridor Multiplayer")
    parser.add_argument(
        "--name",
        type=str,
        default="",
        help="Nome do jogador",
    )
    parser.add_argument(
        "--server-name",
        type=str,
        default=DEFAULT_SERVER_NAME,
        help=f"Nome amigável do servidor no Name Server (padrão: {DEFAULT_SERVER_NAME})",
    )
    parser.add_argument(
        "--ns-host",
        type=str,
        default=DEFAULT_NS_HOST,
        help=f"Host do Pyro5 Name Server (padrão: {DEFAULT_NS_HOST})",
    )
    parser.add_argument(
        "--ns-port",
        type=int,
        default=DEFAULT_NS_PORT,
        help=f"Porta do Pyro5 Name Server (padrão: {DEFAULT_NS_PORT})",
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Executar em modo linha de comando (terminal) em vez de interface gráfica",
    )

    args = parser.parse_args()

    player_name = args.name.strip()
    if not player_name:
        try:
            player_name = input("Informe o seu nome de jogador: ").strip()
        except EOFError:
            player_name = "Jogador"

    if not player_name:
        player_name = "Jogador"

    client = QuoridorClient(
        player_name=player_name,
        server_name=args.server_name,
        ns_host=args.ns_host,
        ns_port=args.ns_port,
    )

    try:
        print(f"Conectando ao servidor '{args.server_name}'...")
        client.connect()
    except Exception as exc:
        logger.error("Falha ao conectar ao servidor: %s", exc)
        print(f"\nErro de conexão: Não foi possível conectar ao servidor via Name Server '{args.server_name}'.")
        print("Certifique-se de que o servidor está rodando ('python run_server.py').")
        sys.exit(1)

    if args.cli:
        run_cli_loop(client)
    else:
        try:
            from ui.gui import QuoridorGUI
            app = QuoridorGUI(client=client)
            app.run()
        except Exception as exc:
            logger.error("Erro na interface gráfica: %s", exc)
            client.disconnect()
            sys.exit(1)


if __name__ == "__main__":
    main()
