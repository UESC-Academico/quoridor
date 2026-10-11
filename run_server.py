import argparse
import sys
from network.config import DEFAULT_NS_HOST, DEFAULT_NS_PORT, DEFAULT_SERVER_NAME, logger
from network.server import start_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor Pyro5 para Quoridor Multiplayer")
    parser.add_argument(
        "--server-name",
        type=str,
        default=DEFAULT_SERVER_NAME,
        help=f"Nome amigável no Name Server (padrão: {DEFAULT_SERVER_NAME})",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="Endereço de rede para vincular o servidor Pyro5 (padrão: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Porta para o servidor Pyro5 (padrão: 0 para seleção automática)",
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
        "--no-auto-ns",
        action="store_true",
        help="Não iniciar o Name Server automaticamente se ele não estiver rodando",
    )

    args = parser.parse_args()

    try:
        daemon, server_instance, ns_thread = start_server(
            server_name=args.server_name,
            host=args.host,
            port=args.port,
            ns_host=args.ns_host,
            ns_port=args.ns_port,
            auto_start_ns=not args.no_auto_ns,
        )
        logger.info("Servidor ativo e pronto para receber conexões. Pressione Ctrl+C para encerrar.")
        daemon.requestLoop()
    except KeyboardInterrupt:
        logger.info("Encerrando servidor...")
        daemon.shutdown()
        sys.exit(0)
    except Exception as exc:
        logger.error("Erro fatal ao executar o servidor: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
