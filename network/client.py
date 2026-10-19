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

    Todos os métodos são decorados com @Pyro5.api.oneway para que o servidor não bloqueie sua
    execução aguardando respostas.
    """

    def __init__(self, client: QuoridorClient) -> None:
        """Inicializa o manipulador de callbacks vinculado à instância do cliente.

        Args:
            client: Instância de `QuoridorClient` que processará os eventos despachados.
        """
        self.client = client

    @Pyro5.api.oneway
    def on_player_joined(
        self, player_info: dict[str, Any], lobby_players: list[dict[str, Any]]
    ) -> None:
        """Callback acionado quando um novo jogador entra na sala.

        Args:
            player_info: Dicionário com id e nome do jogador recém-chegado.
            lobby_players: Lista atualizada de todos os jogadores no lobby.
        """
        self.client._handle_event(
            "player_joined", {"player": player_info, "lobby": lobby_players}
        )

    @Pyro5.api.oneway
    def on_player_left(
        self, player_id: int, lobby_players: list[dict[str, Any]]
    ) -> None:
        """Callback acionado quando um jogador sai da sala ou se desconecta.

        Args:
            player_id: ID do jogador que se desconectou.
            lobby_players: Lista atualizada dos jogadores remanescentes.
        """
        self.client._handle_event(
            "player_left", {"player_id": player_id, "lobby": lobby_players}
        )

    @Pyro5.api.oneway
    def on_game_started(self, initial_state: dict[str, Any]) -> None:
        """Callback acionado quando a partida é iniciada pelo servidor.

        Args:
            initial_state: Dicionário contendo o estado inicial do jogo.
        """
        self.client._handle_event("game_started", initial_state)

    @Pyro5.api.oneway
    def on_game_state_changed(
        self, game_state: dict[str, Any], message: str = ""
    ) -> None:
        """Callback acionado sempre que o estado do jogo se altera (jogadas, paredes, etc.).

        Args:
            game_state: Dicionário com os dados atualizados da partida e tabuleiro.
            message: Mensagem explicativa descrevendo a última ação ocorrida.
        """
        self.client._handle_event(
            "state_changed", {"state": game_state, "message": message}
        )

    @Pyro5.api.oneway
    def on_game_over(
        self, winner_id: int, winner_name: str, game_state: dict[str, Any]
    ) -> None:
        """Callback acionado quando a partida termina com um vencedor.

        Args:
            winner_id: ID do jogador vencedor.
            winner_name: Nome do jogador vencedor.
            game_state: Estado final completo da partida.
        """
        self.client._handle_event(
            "game_over",
            {"winner_id": winner_id, "winner_name": winner_name, "state": game_state},
        )

    @Pyro5.api.oneway
    def on_error(self, message: str) -> None:
        """Callback acionado para mensagens de erro enviadas pelo servidor.

        Args:
            message: Descrição do erro ocorrido.
        """
        self.client._handle_event("error", {"message": message})

    @Pyro5.api.oneway
    def on_assigned_id(self, new_player_id: int) -> None:
        """Callback acionado pelo servidor para sincronizar a alteração do ID do jogador local.

        Args:
            new_player_id: Novo ID atribuído pelo servidor.
        """
        with self.client._lock:
            self.client.player_id = new_player_id
        logger.info("ID do jogador atualizado pelo servidor para: %d", new_player_id)
        self.client._handle_event("player_id_changed", {"player_id": new_player_id})


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
        """Inicializa as configurações de conexão do cliente.

        Args:
            player_name: Nome do jogador local.
            server_name: Nome com o qual o servidor foi registrado no Name Server.
            callback_host: Interface de rede para o Daemon local de callback (padrão: 'localhost').
            callback_port: Porta para o Daemon de callback (0 para porta efêmera aleatória).
            ns_host: Endereço do Pyro5 Name Server.
            ns_port: Porta do Pyro5 Name Server.
        """
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
        self._state_event = threading.Event()
        self.latest_state: dict[str, Any] = {}
        self.listeners: list[Callable[[str, Any], None]] = []
        self.is_connected = False

        self._server_uri: str | None = None
        self._heartbeat_thread: threading.Thread | None = None
        self._heartbeat_stop_event = threading.Event()

    def add_listener(self, listener: Callable[[str, Any], None]) -> None:
        """Registra um ouvinte de eventos (ex: interface gráfica ou CLI).

        Args:
            listener: Função invocada a cada evento no formato `listener(event_type, data)`.
        """
        with self._lock:
            if listener not in self.listeners:
                self.listeners.append(listener)

    def remove_listener(self, listener: Callable[[str, Any], None]) -> None:
        """Remove um ouvinte de eventos previamente registrado.

        Args:
            listener: Função a ser removida da lista de ouvintes.
        """
        with self._lock:
            if listener in self.listeners:
                self.listeners.remove(listener)

    def _handle_event(self, event_type: str, data: Any) -> None:
        """Processa eventos recebidos via callbacks do Pyro5 e despacha aos ouvintes registrados.

        Args:
            event_type: Nome identificador do evento (ex: 'state_changed', 'game_over').
            data: Dados associados ao evento.
        """
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
            self._state_event.set()

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
        """Inicializa o Daemon secundário de callback, resolve o servidor via Name Server e conecta o jogador.

        Returns:
            Dicionário com 'player_id', 'name' e 'game_state' inicial da sala.

        Raises:
            Pyro5.errors.NamingError: Se o Name Server ou o servidor não forem encontrados.
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
        self._server_uri = server_uri
        self.server_proxy = Pyro5.api.Proxy(server_uri)
        self.server_proxy._pyroTimeout = 2.5

        # 3. Registra o jogador no servidor enviando o URI de callback
        result = self.server_proxy.register_player(
            self.player_name, str(self.callback_uri)
        )
        self.player_id = result["player_id"]

        with self._lock:
            self.latest_state = result.get("game_state", {})
            self.is_connected = True

        # Inicia o monitoramento de heartbeat em background
        self._start_heartbeat()

        logger.info(
            "Conectado com sucesso ao servidor '%s'! Atribuído Player ID: %d",
            self.server_name,
            self.player_id,
        )
        return result

    def _notify_connection_lost(self, reason: str = "") -> None:
        """Notifica os ouvintes que a conexão com o servidor foi interrompida."""
        with self._lock:
            if not self.is_connected:
                return
            self.is_connected = False
        logger.warning("Conexão com o servidor perdida: %s", reason)
        self._handle_event("connection_lost", {"message": reason})

    def _start_heartbeat(self) -> None:
        """Inicializa a thread de verificação de liveness do servidor."""
        self._heartbeat_stop_event.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name=f"ClientHeartbeat-{self.player_name}",
        )
        self._heartbeat_thread.start()

    def _heartbeat_loop(self) -> None:
        """Pinga periodicamente o servidor para detectar quedas precocemente."""
        if not self._server_uri:
            return

        try:
            with Pyro5.api.Proxy(self._server_uri) as hb_proxy:
                hb_proxy._pyroTimeout = 2.0
                while not self._heartbeat_stop_event.wait(timeout=2.0):
                    with self._lock:
                        if not self.is_connected:
                            break
                    try:
                        hb_proxy.ping()
                    except Exception as exc:  # noqa: BLE001
                        with self._lock:
                            if not self.is_connected:
                                break
                        logger.warning("Heartbeat falhou ao contatar servidor: %s", exc)
                        self._notify_connection_lost(
                            f"Servidor inacessível ou desconectado: {exc}"
                        )
                        break
        except Exception as exc:  # noqa: BLE001
            logger.debug("Aviso ao encerrar proxy do heartbeat: %s", exc)

    def _call_remote(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        """Executa uma chamada RPC thread-safe no proxy do servidor.

        Args:
            method_name: Nome do método exposto no QuoridorServer.
            *args: Argumentos posicionais.
            **kwargs: Argumentos nomeados.

        Returns:
            Resposta retornada pelo servidor remoto.
        """
        with self._lock:
            if not self.server_proxy or not self.is_connected:
                raise RuntimeError("Cliente não conectado ao servidor.")
            self.server_proxy._pyroClaimOwnership()
            proxy = self.server_proxy

        try:
            method = getattr(proxy, method_name)
            return method(*args, **kwargs)
        except (
            Pyro5.errors.CommunicationError,
            Pyro5.errors.ConnectionClosedError,
            Pyro5.errors.TimeoutError,
            ConnectionRefusedError,
            ConnectionResetError,
            OSError,
        ) as exc:
            logger.error(
                "Falha de comunicação RPC com o servidor (%s): %s", method_name, exc
            )
            self._notify_connection_lost(
                f"Falha de comunicação ao executar '{method_name}': {exc}"
            )
            raise

    def _wait_for_state_sync(self, timeout: float = 1.0) -> None:
        """Aguarda a sincronização do estado local via callback ou recorre ao RPC de fallback.

        Garante que chamadas que alteram o estado da partida (ex: move_player, place_wall)
        só retornem após o `latest_state` local ter sido devidamente atualizado.
        """
        if not self._state_event.wait(timeout=timeout):
            with self._lock:
                if not self.is_connected:
                    return
            try:
                fresh_state = self._call_remote("get_game_state")
                with self._lock:
                    self.latest_state = fresh_state
                    self._state_event.set()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Falha ao sincronizar estado via fallback RPC: %s", exc)

    def start_game(self) -> tuple[bool, str]:
        """Solicita ao servidor o início da partida.

        Returns:
            Tupla (sucesso, mensagem_servidor).
        """
        self._state_event.clear()
        try:
            res = self._call_remote("start_game", self.player_id)
            if isinstance(res, (tuple, list)) and res[0]:
                self._wait_for_state_sync()
            return tuple(res)
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def move_player(
        self, new_position: tuple[int, int] | list[int]
    ) -> tuple[bool, str]:
        """Envia solicitação de movimentação do peão para o servidor.

        Args:
            new_position: Coordenadas (linha, coluna) de destino.

        Returns:
            Tupla (sucesso, mensagem_servidor).
        """
        self._state_event.clear()
        try:
            res = self._call_remote("move_player", self.player_id, list(new_position))
            if isinstance(res, (tuple, list)) and res[0]:
                self._wait_for_state_sync()
            return tuple(res)
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def place_wall(
        self, position: tuple[int, int] | list[int], orientation: str
    ) -> tuple[bool, str]:
        """Envia solicitação de posicionamento de parede para o servidor.

        Args:
            position: Posição de ancoragem (0 a 7, 0 a 7).
            orientation: Orientação ('H' ou 'V').

        Returns:
            Tupla (sucesso, mensagem_servidor).
        """
        self._state_event.clear()
        try:
            res = self._call_remote(
                "place_wall", self.player_id, list(position), orientation
            )
            if isinstance(res, (tuple, list)) and res[0]:
                self._wait_for_state_sync()
            return tuple(res)
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def get_valid_moves(self) -> list[tuple[int, int]]:
        """Consulta os movimentos válidos para o jogador.

        Returns:
            Lista de coordenadas (linha, coluna) alcançáveis pelo jogador local.
        """
        try:
            moves = self._call_remote("get_valid_moves", self.player_id)
            return [tuple(m) for m in moves]
        except Exception as exc:  # noqa: BLE001
            logger.error("Erro ao consultar movimentos válidos: %s", exc)
            return []

    def get_game_state(self) -> dict[str, Any]:
        """Retorna uma cópia do estado mais recente recebido via callbacks.

        Returns:
            Dicionário com os dados atuais de jogo e lobby.
        """
        with self._lock:
            return dict(self.latest_state)

    def reset_game(self) -> tuple[bool, str]:
        """Solicita o reinício da partida ao servidor.

        Returns:
            Tupla (sucesso, mensagem_servidor).
        """
        self._state_event.clear()
        try:
            res = self._call_remote("reset_game", self.player_id)
            if isinstance(res, (tuple, list)) and res[0]:
                self._wait_for_state_sync()
            return tuple(res)
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def disconnect(self) -> None:
        """Desconecta do servidor e desliga o Daemon local de callbacks."""
        self._heartbeat_stop_event.set()
        with self._lock:
            if not self.is_connected and not self.server_proxy:
                return
            self.is_connected = False
            player_id = self.player_id
            self.player_id = None
            proxy = self.server_proxy
            self.server_proxy = None
            daemon = self.daemon
            self.daemon = None

        logger.info("Desconectando cliente %s (ID %s)...", self.player_name, player_id)

        # Informa ao servidor
        if proxy and player_id is not None:
            try:
                proxy._pyroClaimOwnership()
                proxy._pyroTimeout = 1.5
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
