import argparse
import sys
import time
from network.config import DEFAULT_NS_HOST, DEFAULT_NS_PORT, DEFAULT_SERVER_NAME, logger
from network.client import QuoridorClient


def run_cli_loop(client: QuoridorClient) -> None:
    """Modo texto interativo no terminal com telas de tabuleiro e lobby."""
    from ui.cli import run_network_cli
    run_network_cli(client)


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
