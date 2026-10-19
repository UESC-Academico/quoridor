from __future__ import annotations

import threading
from collections.abc import Callable

import Pyro5.api

from network.config import logger


class ClientHeartbeatMonitor:
    """Monitor de integridade de conexão executado em thread secundária no cliente.

    Realiza pings periódicos contra o servidor utilizando um proxy Pyro5 dedicado,
    garantindo que o socket principal não seja bloqueado e detectando quedas do servidor
    de maneira rápida e confiável.
    """

    def __init__(
        self,
        player_name: str,
        interval: float = 2.0,
        timeout: float = 2.0,
    ) -> None:
        """Inicializa as configurações do monitor de heartbeat.

        Args:
            player_name: Nome do jogador associado para identificação da thread e logs.
            interval: Intervalo em segundos entre cada ping.
            timeout: Tempo limite em segundos para aguardar resposta do ping.
        """
        self.player_name = player_name
        self.interval = interval
        self.timeout = timeout

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._server_uri: str | None = None
        self._on_lost: Callable[[str], None] | None = None

    def start(
        self,
        server_uri: str,
        on_connection_lost: Callable[[str], None],
    ) -> None:
        """Inicializa a thread de monitoramento em segundo plano.

        Args:
            server_uri: Endereço URI Pyro5 do servidor a ser monitorado.
            on_connection_lost: Função de callback acionada caso o servidor pare de responder.
        """
        self.stop()
        self._server_uri = server_uri
        self._on_lost = on_connection_lost
        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name=f"HeartbeatThread-{self.player_name}",
        )
        self._thread.start()
        logger.debug("Monitor de Heartbeat iniciado para %s.", self.player_name)

    def stop(self) -> None:
        """Sinaliza a interrupção da thread de monitoramento e aguarda sua finalização."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.timeout + 0.5)
        self._thread = None

    def _run(self) -> None:
        """Loop contínuo de ping executado na thread de monitoramento."""
        if not self._server_uri:
            return

        try:
            with Pyro5.api.Proxy(self._server_uri) as proxy:
                proxy._pyroTimeout = self.timeout

                while not self._stop_event.wait(timeout=self.interval):
                    try:
                        proxy.ping()
                    except Exception as exc:  # noqa: BLE001
                        if self._stop_event.is_set():
                            break

                        logger.warning(
                            "Heartbeat detectou falha no servidor: %s", exc
                        )
                        if self._on_lost:
                            self._on_lost(f"Servidor inacessível: {exc}")
                        break
        except Exception as exc:  # noqa: BLE001
            logger.debug("Aviso ao encerrar proxy do heartbeat: %s", exc)
