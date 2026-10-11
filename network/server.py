from __future__ import annotations
import logging
import threading
import time
from typing import Any
import Pyro5.api
import Pyro5.errors
from core.game import QuoridorGame
from core.models import Wall
from network.config import (
    DEFAULT_NS_HOST,
    DEFAULT_NS_PORT,
    DEFAULT_SERVER_NAME,
    MAX_PLAYERS,
    ALLOWED_PLAYER_COUNTS,
    configure_pyro,
    logger,
)
from network.protocol import serialize_game_state


@Pyro5.api.expose
@Pyro5.api.behavior(instance_mode="single")
class QuoridorServer:
    """Servidor Quoridor multiplayer com estado compartilhado em instância única.

    Utiliza Pyro5 e threading.Lock para garantir concorrência segura entre múltiplos jogadores.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.game: QuoridorGame | None = None
        self.lobby: list[dict[str, Any]] = []
        self.callbacks: dict[int, str] = {}
        self.max_players = MAX_PLAYERS
        logger.info("Instância do QuoridorServer inicializada.")

    # -------------------------------------------------------------------------
    # Métodos Internos de Broadcast e Notificação
    # -------------------------------------------------------------------------

    def _broadcast(self, action_name: str, *args: Any, **kwargs: Any) -> None:
        """Envia uma notificação assíncrona (oneway) para todos os clientes ativos.

        Remove de forma resiliente os callbacks que apresentarem falha de comunicação.
        """
        with self.lock:
            callbacks_snapshot = list(self.callbacks.items())

        dead_players: list[int] = []
        callbacks_copy = callbacks_snapshot
        for pid, uri in callbacks_copy:
            try:
                with Pyro5.api.Proxy(uri) as proxy:
                    proxy._pyroTimeout = 3.0
                    method = getattr(proxy, action_name, None)
                    if method is not None:
                        method(*args, **kwargs)
            except Exception as exc:
                logger.warning(
                    "Falha ao enviar callback '%s' para jogador %d (%s): %s",
                    action_name, pid, uri, exc
                )
                dead_players.append(pid)

        if dead_players:
            with self.lock:
                for pid in dead_players:
                    if pid in self.callbacks:
                        del self.callbacks[pid]
                    # Remove do lobby se o jogo ainda não tiver iniciado
                    if self.game is None or not self.game.game_started:
                        self.lobby = [p for p in self.lobby if p["id"] != pid]

    def _get_game_state_unlocked(self, message: str = "") -> dict[str, Any]:
        """Gera o dicionário de estado atual sem adquirir o lock (uso interno quando o lock já está retido)."""
        return serialize_game_state(self.game, self.lobby, message)

    # -------------------------------------------------------------------------
    # Gerenciamento de Sala e Jogadores (Lobby)
    # -------------------------------------------------------------------------

    def register_player(self, player_name: str, callback_uri: str) -> dict[str, Any]:
        """Registra um novo jogador no lobby da partida.

        Requisitos:
        - Máximo de 4 jogadores no lobby.
        - Não permite novas conexões caso o jogo já tenha iniciado.
        """
        cleaned_name = (player_name or "").strip()
        if not cleaned_name:
            raise ValueError("O nome do jogador não pode ser vazio.")
        if not callback_uri:
            raise ValueError("URI de callback obrigatória para conexão bidirecional.")

        with self.lock:
            if self.game is not None and self.game.game_started:
                raise ValueError("A partida já começou! Não é possível entrar agora.")

            if len(self.lobby) >= self.max_players:
                raise ValueError(
                    f"O lobby está cheio! Limite máximo de {self.max_players} jogadores atingido."
                )

            new_id = len(self.lobby) + 1
            player_info = {
                "id": new_id,
                "name": cleaned_name,
                "callback_uri": callback_uri,
            }
            self.lobby.append(player_info)
            self.callbacks[new_id] = callback_uri

            logger.info(
                "Jogador registrado: ID %d, Nome '%s'. Total no lobby: %d/%d",
                new_id, cleaned_name, len(self.lobby), self.max_players
            )
            state = self._get_game_state_unlocked(f"{cleaned_name} entrou no lobby.")

        # Notifica todos os jogadores sobre a entrada
        self._broadcast("on_player_joined", player_info, state["lobby"])
        self._broadcast("on_game_state_changed", state, f"{cleaned_name} entrou no lobby.")

        return {
            "player_id": new_id,
            "name": cleaned_name,
            "game_state": state,
        }

    def unregister_player(self, player_id: int) -> tuple[bool, str]:
        """Desconecta um jogador do servidor."""
        with self.lock:
            found = False
            removed_name = ""
            for p in self.lobby:
                if p["id"] == player_id:
                    found = True
                    removed_name = p["name"]
                    break

            if not found and player_id not in self.callbacks:
                return False, f"Jogador {player_id} não encontrado."

            if player_id in self.callbacks:
                del self.callbacks[player_id]

            if self.game is not None and self.game.game_started:
                # Jogo em andamento: notifica desistência / saída
                msg = f"Jogador {player_id} ({removed_name}) desconectou da partida em andamento."
                logger.warning(msg)
                state = self._get_game_state_unlocked(msg)
            else:
                # Lobby: remove e reorganiza IDs para manter ordem sequencial
                self.lobby = [p for p in self.lobby if p["id"] != player_id]
                old_callbacks = dict(self.callbacks)
                self.callbacks.clear()
                for idx, p in enumerate(self.lobby, start=1):
                    old_id = p["id"]
                    p["id"] = idx
                    if old_id in old_callbacks:
                        self.callbacks[idx] = old_callbacks[old_id]

                msg = f"Jogador {removed_name} saiu do lobby."
                logger.info(msg)
                state = self._get_game_state_unlocked(msg)

        self._broadcast("on_player_left", player_id, state["lobby"])
        self._broadcast("on_game_state_changed", state, msg)
        return True, msg

    def start_game(self, player_id: int | None = None) -> tuple[bool, str]:
        """Inicia a partida de Quoridor.

        Requisito: Inicia apenas quando houver exatamente 2 ou 4 jogadores conectados.
        """
        with self.lock:
            if self.game is not None and self.game.game_started:
                return False, "A partida já está em andamento!"

            num_players = len(self.lobby)
            if num_players not in ALLOWED_PLAYER_COUNTS:
                msg = (
                    f"A partida só pode ser iniciada com 2 ou 4 jogadores! "
                    f"Atualmente há {num_players} jogador(es) no lobby."
                )
                logger.warning(msg)
                return False, msg

            # Cria o jogo principal do Quoridor
            self.game = QuoridorGame(num_players=num_players)
            for p in self.lobby:
                assigned_id = self.game.add_player(p["name"])
                logger.debug("Jogador '%s' vinculado ao ID de jogo %d", p["name"], assigned_id)

            logger.info("Partida iniciada com sucesso com %d jogadores!", num_players)
            state = self._get_game_state_unlocked("A partida foi iniciada!")

        # Notifica todos os clientes via broadcast
        self._broadcast("on_game_started", state)
        self._broadcast("on_game_state_changed", state, "Partida iniciada! Vez do Jogador 1.")
        return True, f"Partida iniciada com {num_players} jogadores!"

    # -------------------------------------------------------------------------
    # Ações de Jogo (Movimentação e Paredes)
    # -------------------------------------------------------------------------

    def move_player(
        self, player_id: int, new_position: tuple[int, int] | list[int]
    ) -> tuple[bool, str]:
        """Executa a movimentação do peão de um jogador no tabuleiro."""
        with self.lock:
            if self.game is None or not self.game.game_started:
                return False, "O jogo ainda não começou!"

            if self.game.winner is not None:
                return False, "O jogo já terminou!"

            if self.game.turn != player_id:
                return False, f"Não é a sua vez! Vez do Jogador {self.game.turn}."

            target_pos = (int(new_position[0]), int(new_position[1]))
            success, msg = self.game.move_player(player_id, target_pos)

            if not success:
                return False, msg

            winner = self.game.winner
            winner_name = self.game.players[winner].name if winner else ""
            current_turn = self.game.turn
            p_name = self.game.players[player_id].name
            state = self._get_game_state_unlocked(msg)

        # Broadcast da alteração de estado
        if winner:
            logger.info("Fim de jogo! Jogador %d (%s) venceu!", winner, winner_name)
            self._broadcast("on_game_over", winner, winner_name, state)
            self._broadcast("on_game_state_changed", state, f"Vitória de {winner_name}!")
        else:
            turn_msg = f"{p_name} moveu para {target_pos}. Vez do Jogador {current_turn}."
            self._broadcast("on_game_state_changed", state, turn_msg)

        return True, msg

    def place_wall(
        self, player_id: int, position: tuple[int, int] | list[int], orientation: str
    ) -> tuple[bool, str]:
        """Posiciona uma parede no tabuleiro para o jogador."""
        with self.lock:
            if self.game is None or not self.game.game_started:
                return False, "O jogo ainda não começou!"

            if self.game.winner is not None:
                return False, "O jogo já terminou!"

            if self.game.turn != player_id:
                return False, f"Não é a sua vez! Vez do Jogador {self.game.turn}."

            wall_pos = (int(position[0]), int(position[1]))
            clean_orientation = orientation.strip().upper()
            wall = Wall(position=wall_pos, orientation=clean_orientation)

            success, msg = self.game.place_wall(player_id, wall)
            if not success:
                return False, msg

            current_turn = self.game.turn
            p_name = self.game.players[player_id].name
            state = self._get_game_state_unlocked(msg)

        wall_msg = (
            f"{p_name} posicionou parede em {wall_pos} ({clean_orientation}). "
            f"Vez do Jogador {current_turn}."
        )
        self._broadcast("on_game_state_changed", state, wall_msg)
        return True, msg

    # -------------------------------------------------------------------------
    # Consultas de Estado
    # -------------------------------------------------------------------------

    def get_game_state(self) -> dict[str, Any]:
        """Retorna o estado completo atual do jogo e do lobby."""
        with self.lock:
            return self._get_game_state_unlocked()

    def get_valid_moves(self, player_id: int) -> list[tuple[int, int]]:
        """Retorna os movimentos válidos para o jogador no turno atual."""
        with self.lock:
            if self.game is None or not self.game.game_started or self.game.winner:
                return []
            if player_id not in self.game.players:
                return []
            return self.game.get_valid_moves(player_id)

    def can_place_wall(
        self, player_id: int, position: tuple[int, int] | list[int], orientation: str
    ) -> tuple[bool, str]:
        """Verifica preventivamente se a colocação de uma parede é válida."""
        with self.lock:
            if self.game is None or not self.game.game_started:
                return False, "O jogo ainda não começou!"
            wall = Wall(position=(int(position[0]), int(position[1])), orientation=orientation.strip().upper())
            return self.game.can_place_wall(player_id, wall)

    def reset_game(self, player_id: int | None = None) -> tuple[bool, str]:
        """Reinicia o jogo, retornando ao lobby com os jogadores conectados."""
        with self.lock:
            self.game = None
            msg = "A partida foi reiniciada para o lobby."
            state = self._get_game_state_unlocked(msg)

        logger.info(msg)
        self._broadcast("on_game_state_changed", state, msg)
        return True, msg


# -----------------------------------------------------------------------------
# Função Auxiliar de Inicialização do Servidor
# -----------------------------------------------------------------------------

def start_server(
    server_name: str = DEFAULT_SERVER_NAME,
    host: str = "localhost",
    port: int = 0,
    ns_host: str = DEFAULT_NS_HOST,
    ns_port: int | None = DEFAULT_NS_PORT,
    auto_start_ns: bool = True,
) -> tuple[Pyro5.api.Daemon, QuoridorServer, threading.Thread | None]:
    """Inicializa o servidor Pyro5, registra no Name Server e inicia o loop."""
    configure_pyro()
    from Pyro5.api import config
    if ns_host:
        config.NS_HOST = ns_host
    if ns_port:
        config.NS_PORT = ns_port

    ns_thread: threading.Thread | None = None

    # Tenta localizar o Name Server (pyro5-ns)
    try:
        ns = Pyro5.api.locate_ns(host=ns_host, port=ns_port)
        logger.info("Name Server do Pyro5 localizado com sucesso em %s:%s", ns_host, ns_port)
    except Pyro5.errors.NamingError:
        if auto_start_ns:
            logger.info("Name Server não encontrado. Iniciando Name Server embutido em %s:%s...", ns_host, ns_port)
            ns_thread = threading.Thread(
                target=Pyro5.api.start_ns_loop,
                kwargs={"host": ns_host, "port": ns_port},
                daemon=True,
                name="EmbeddedNameServerThread"
            )
            ns_thread.start()
            time.sleep(0.5)
            ns = Pyro5.api.locate_ns(host=ns_host, port=ns_port)
            logger.info("Name Server embutido inicializado e conectado!")
        else:
            raise RuntimeError(
                f"Name Server não encontrado em {ns_host}:{ns_port}. "
                f"Inicie o Name Server com o comando 'pyro5-ns' ou utilize a flag --auto-ns."
            )

    # Cria o daemon Pyro5 do Servidor
    daemon = Pyro5.api.Daemon(host=host, port=port)
    server_instance = QuoridorServer()
    server_uri = daemon.register(server_instance)

    # Registra no Name Server com nome amigável
    ns.register(server_name, server_uri)

    logger.info("=" * 60)
    logger.info("Servidor Quoridor publicado com sucesso!")
    logger.info("Nome amigável no Name Server: PYRONAME:%s", server_name)
    logger.info("URI direta Pyro: %s", server_uri)
    logger.info("=" * 60)

    return daemon, server_instance, ns_thread
