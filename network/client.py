from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import Pyro5.api
import Pyro5.errors

from network.config import (
    DEFAULT_NS_HOST,
    DEFAULT_NS_PORT,
    DEFAULT_SERVER_NAME,
    configure_pyro,
    logger,
)


@Pyro5.api.expose
class GameClientCallback:
    """Objeto remoto registrado no Daemon do cliente para receber notificações (callbacks) do servidor.

    Conforme os requisitos técnicos, todos os métodos são decorados com @Pyro5.api.oneway
    para que o servidor não bloqueie sua execução aguardando respostas.
    """

    def __init__(self, client: QuoridorClient) -> None:
        self.client = client

    @Pyro5.api.oneway
    def on_player_joined(
        self, player_info: dict[str, Any], lobby_players: list[dict[str, Any]]
    ) -> None:
        """Callback acionado quando um novo jogador entra na sala."""
        self.client._handle_event(
            "player_joined", {"player": player_info, "lobby": lobby_players}
        )

    @Pyro5.api.oneway
    def on_player_left(
        self, player_id: int, lobby_players: list[dict[str, Any]]
    ) -> None:
        """Callback acionado quando um jogador sai da sala."""
        self.client._handle_event(
            "player_left", {"player_id": player_id, "lobby": lobby_players}
        )

    @Pyro5.api.oneway
    def on_game_started(self, initial_state: dict[str, Any]) -> None:
        """Callback acionado quando a partida é iniciada."""
        self.client._handle_event("game_started", initial_state)

    @Pyro5.api.oneway
    def on_game_state_changed(
        self, game_state: dict[str, Any], message: str = ""
    ) -> None:
        """Callback acionado sempre que o estado do jogo se altera (jogadas, paredes, etc.)."""
        self.client._handle_event(
            "state_changed", {"state": game_state, "message": message}
        )

    @Pyro5.api.oneway
    def on_game_over(
        self, winner_id: int, winner_name: str, game_state: dict[str, Any]
    ) -> None:
        """Callback acionado quando a partida termina com um vencedor."""
        self.client._handle_event(
            "game_over",
            {"winner_id": winner_id, "winner_name": winner_name, "state": game_state},
        )

    @Pyro5.api.oneway
    def on_error(self, message: str) -> None:
        """Callback acionado para mensagens de erro enviadas pelo servidor."""
        self.client._handle_event("error", {"message": message})


class QuoridorClient:
    """Cliente Quoridor multiplayer com arquitetura de callbacks bidirecionais.

    Executa um Daemon próprio do Pyro5 em uma thread secundária de background
    e comunica seu URI de callback ao servidor ao se conectar.
    """

    def __init__(
        self,
        player_name: str,
        server_name: str = DEFAULT_SERVER_NAME,
        callback_host: str = "localhost",
        callback_port: int = 0,
        ns_host: str = DEFAULT_NS_HOST,
        ns_port: int | None = DEFAULT_NS_PORT,
    ) -> None:
        self.player_name = (player_name or "").strip()
        self.server_name = server_name
        self.callback_host = callback_host
        self.callback_port = callback_port
        self.ns_host = ns_host
        self.ns_port = ns_port

        self.player_id: int | None = None
        self.server_proxy: Pyro5.api.Proxy | None = None
        self.daemon: Pyro5.api.Daemon | None = None
        self.daemon_thread: threading.Thread | None = None
        self.callback_handler: GameClientCallback | None = None
        self.callback_uri: Pyro5.api.URI | None = None

        self._lock = threading.Lock()
        self.latest_state: dict[str, Any] = {}
        self.listeners: list[Callable[[str, Any], None]] = []
        self.is_connected = False

    def add_listener(self, listener: Callable[[str, Any], None]) -> None:
        """Registra um ouvinte de eventos (ex: interface gráfica ou CLI)."""
        with self._lock:
            if listener not in self.listeners:
                self.listeners.append(listener)

    def remove_listener(self, listener: Callable[[str, Any], None]) -> None:
        """Remove um ouvinte de eventos."""
        with self._lock:
            if listener in self.listeners:
                self.listeners.remove(listener)

    def _handle_event(self, event_type: str, data: Any) -> None:
        """Processa eventos recebidos via callbacks do Pyro5 e despacha aos ouvintes registrados."""
        with self._lock:
            if (
                event_type == "state_changed"
                and isinstance(data, dict)
                and "state" in data
            ):
                self.latest_state = data["state"]
            elif event_type in ("game_started", "game_over"):
                if isinstance(data, dict) and "state" in data:
                    self.latest_state = data["state"]
                elif isinstance(data, dict):
                    self.latest_state = data

            listeners_copy = list(self.listeners)

        for listener in listeners_copy:
            try:
                listener(event_type, data)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Erro no processamento do ouvinte para o evento '%s': %s",
                    event_type,
                    exc,
                )

    def connect(self) -> dict[str, Any]:
        """Inicializa o Daemon secundário de callback, resolve o servidor via Name Server

        e conecta o jogador.
        """
        configure_pyro()

        # 1. Cria e inicia o Daemon de Callbacks em background
        self.daemon = Pyro5.api.Daemon(host=self.callback_host, port=self.callback_port)
        self.callback_handler = GameClientCallback(self)
        self.callback_uri = self.daemon.register(self.callback_handler)

        self.daemon_thread = threading.Thread(
            target=self.daemon.requestLoop,
            daemon=True,
            name=f"PyroDaemonClient-{self.player_name}",
        )
        self.daemon_thread.start()
        logger.info(
            "Daemon do cliente inicializado em thread secundária. Callback URI: %s",
            self.callback_uri,
        )

        # 2. Conecta ao servidor via resolução do Name Server (PYRONAME)
        from Pyro5.api import config

        if self.ns_host:
            config.NS_HOST = self.ns_host
        if self.ns_port:
            config.NS_PORT = self.ns_port

        Pyro5.api.locate_ns(host=self.ns_host, port=self.ns_port)
        if self.ns_host and self.ns_port:
            server_uri = f"PYRONAME:{self.server_name}@{self.ns_host}:{self.ns_port}"
        else:
            server_uri = f"PYRONAME:{self.server_name}"
        self.server_proxy = Pyro5.api.Proxy(server_uri)
        self.server_proxy._pyroTimeout = 10.0

        # 3. Registra o jogador no servidor enviando o URI de callback
        result = self.server_proxy.register_player(
            self.player_name, str(self.callback_uri)
        )
        self.player_id = result["player_id"]

        with self._lock:
            self.latest_state = result.get("game_state", {})
            self.is_connected = True

        logger.info(
            "Conectado com sucesso ao servidor '%s'! Atribuído Player ID: %d",
            self.server_name,
            self.player_id,
        )
        return result

    def _call_remote(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            if not self.server_proxy or not self.is_connected:
                raise RuntimeError("Cliente não conectado ao servidor.")
            self.server_proxy._pyroClaimOwnership()
            method = getattr(self.server_proxy, method_name)
            return method(*args, **kwargs)

    def start_game(self) -> tuple[bool, str]:
        """Solicita ao servidor o início da partida."""
        try:
            return self._call_remote("start_game", self.player_id)
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def move_player(
        self, new_position: tuple[int, int] | list[int]
    ) -> tuple[bool, str]:
        """Envia solicitação de movimentação do peão para o servidor."""
        try:
            return self._call_remote("move_player", self.player_id, list(new_position))
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def place_wall(
        self, position: tuple[int, int] | list[int], orientation: str
    ) -> tuple[bool, str]:
        """Envia solicitação de posicionamento de parede para o servidor."""
        try:
            return self._call_remote(
                "place_wall", self.player_id, list(position), orientation
            )
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def get_valid_moves(self) -> list[tuple[int, int]]:
        """Consulta os movimentos válidos para o jogador."""
        try:
            moves = self._call_remote("get_valid_moves", self.player_id)
            return [tuple(m) for m in moves]
        except Exception as exc:  # noqa: BLE001
            logger.error("Erro ao consultar movimentos válidos: %s", exc)
            return []

    def get_game_state(self) -> dict[str, Any]:
        """Retorna a cópia do estado mais recente recebido via callbacks."""
        with self._lock:
            return dict(self.latest_state)

    def reset_game(self) -> tuple[bool, str]:
        """Solicita o reinício da partida."""
        try:
            return self._call_remote("reset_game", self.player_id)
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def disconnect(self) -> None:
        """Desconecta do servidor e desliga o Daemon local de callbacks."""
        with self._lock:
            if not self.is_connected:
                return
            self.is_connected = False
            player_id = self.player_id
            self.player_id = None
            proxy = self.server_proxy
            daemon = self.daemon

        logger.info("Desconectando cliente %s (ID %s)...", self.player_name, player_id)

        # Informa ao servidor
        if proxy and player_id is not None:
            try:
                proxy._pyroClaimOwnership()
                proxy.unregister_player(player_id)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Aviso ao desregistrar do servidor: %s", exc)
            finally:
                try:
                    proxy._pyroRelease()
                except (Pyro5.errors.PyroError, OSError) as exc:
                    logger.debug("Aviso ao liberar proxy: %s", exc)

        # Desliga o Daemon de callback
        if daemon:
            try:
                daemon.shutdown()
            except Exception as exc:  # noqa: BLE001
                logger.debug("Aviso ao desligar daemon do cliente: %s", exc)

        logger.info("Cliente desconectado com sucesso.")
