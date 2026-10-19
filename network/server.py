from __future__ import annotations

import threading
import time
from typing import Any

import Pyro5.api
import Pyro5.errors

from core.game import QuoridorGame
from core.models import Wall
from network.broadcaster import Broadcaster
from network.config import (
    ALLOWED_PLAYER_COUNTS,
    DEFAULT_NS_HOST,
    DEFAULT_NS_PORT,
    DEFAULT_SERVER_NAME,
    MAX_PLAYERS,
    configure_pyro,
    logger,
)
from network.lobby import LobbyManager
from network.protocol import serialize_game_state

__all__ = ["QuoridorServer", "start_server"]


@Pyro5.api.expose
@Pyro5.api.behavior(instance_mode="single")
class QuoridorServer:
    """Servidor Quoridor multiplayer com estado compartilhado em instância única.

    Utiliza Pyro5 e threading.Lock para garantir concorrência segura entre múltiplos jogadores.
    Delega a gestão da sala de espera para `LobbyManager` e o envio de callbacks para `Broadcaster`.
    """

    def __init__(self) -> None:
        """Inicializa as instâncias de sincronização, sala de espera e regras de jogo."""
        self.lock = threading.Lock()
        self.game: QuoridorGame | None = None
        self.lobby = LobbyManager(max_players=MAX_PLAYERS)
        self.broadcaster = Broadcaster()
        logger.info("Instância do QuoridorServer inicializada.")

    # -------------------------------------------------------------------------
    # Métodos Internos de Notificação e Broadcast
    # -------------------------------------------------------------------------

    def _broadcast(self, action_name: str, *args: Any, **kwargs: Any) -> None:
        """Envia notificação assíncrona (oneway) para todos os jogadores conectados.

        Purga de forma resiliente qualquer cliente que falhar durante a chamada
        e atualiza o estado do jogo caso um jogador ativo tenha caído.

        Args:
            action_name: Nome do método de callback a ser executado nos clientes.
            *args: Argumentos posicionais do callback.
            **kwargs: Argumentos nomeados do callback.
        """
        with self.lock:
            callbacks_snapshot = self.lobby.get_callbacks_snapshot()

        dead_players = self.broadcaster.broadcast(
            callbacks_snapshot, action_name, *args, **kwargs
        )

        if dead_players:
            game_over_event: tuple[int, str, dict[str, Any]] | None = None
            state_changed_event: tuple[dict[str, Any], str] | None = None

            with self.lock:
                for pid in dead_players:
                    self.lobby.remove(pid)

                    if (
                        self.game is not None
                        and self.game.game_started
                        and self.game.winner is None
                        and pid in self.game.players
                        and self.game.players[pid].is_active
                    ):
                        state, msg, is_over = self._eliminate_player_unlocked(
                            pid, "perdeu a conexão"
                        )
                        if is_over:
                            winner = self.game.winner
                            winner_name = (
                                self.game.players[winner].name if winner else ""
                            )
                            game_over_event = (winner, winner_name, state)
                        state_changed_event = (state, msg)
                    elif self.game is None or not self.game.game_started:
                        id_updates = self.lobby.reorganize()
                        for uri, new_id in id_updates:
                            self.broadcaster.notify_one(
                                uri, "on_assigned_id", new_id
                            )

                # Se todos os jogadores caíram ou saíram, reseta completamente o servidor
                if not self.lobby.has_active_callbacks():
                    logger.info(
                        "Todos os jogadores foram desconectados. "
                        "Resetando o servidor para o estado inicial de espera."
                    )
                    self.game = None
                    self.lobby.clear()
                    game_over_event = None
                    state_changed_event = None

            if game_over_event and self.lobby.has_active_callbacks():
                self._broadcast("on_game_over", *game_over_event)
            if state_changed_event and self.lobby.has_active_callbacks():
                self._broadcast("on_game_state_changed", *state_changed_event)

    def _eliminate_player_unlocked(
        self, player_id: int, reason: str = "desconectou"
    ) -> tuple[dict[str, Any], str, bool]:
        """Elimina um jogador da partida em andamento e atualiza turno ou vencedor.

        Assume que o lock da instância já foi adquirido pela rotina chamadora.

        Args:
            player_id: ID do jogador eliminado.
            reason: Motivo textual da eliminação.

        Returns:
            Tupla (estado_serializado, mensagem_resultado, eh_fim_de_jogo).
        """
        player_name = (
            self.game.players[player_id].name
            if (self.game and player_id in self.game.players)
            else self.lobby.get_player_name(player_id)
        )

        self.lobby.remove(player_id)

        if self.game is None or not self.game.game_started:
            state = self._get_game_state_unlocked(f"{player_name} saiu.")
            return state, f"{player_name} saiu.", False

        winner_id = self.game.eliminate_player(player_id)
        active_players = [p for p in self.game.players.values() if p.is_active]

        if winner_id is not None:
            winner_name = self.game.players[winner_id].name
            msg = (
                f"{player_name} {reason} e foi eliminado! "
                f"Fim de jogo: {winner_name} (P{winner_id}) é o único restante e venceu a partida!"
            )
            logger.info(msg)
            state = self._get_game_state_unlocked(msg)
            return state, msg, True
        else:
            if not active_players or not self.lobby.has_active_callbacks():
                msg = f"{player_name} {reason}. Não há mais jogadores ativos."
                logger.info(msg)
                self.game = None
                self.lobby.clear()
                state = self._get_game_state_unlocked(msg)
                return state, msg, True

            current_turn = self.game.turn
            turn_name = (
                self.game.players[current_turn].name
                if current_turn in self.game.players
                else f"Jogador {current_turn}"
            )
            msg = (
                f"{player_name} {reason} e foi eliminado! "
                f"Restam {len(active_players)} jogadores na partida. Vez de {turn_name} (P{current_turn})."
            )
            logger.info(msg)
            state = self._get_game_state_unlocked(msg)
            return state, msg, False

    def _get_game_state_unlocked(self, message: str = "") -> dict[str, Any]:
        """Gera o dicionário de estado atual sem adquirir o lock.

        Args:
            message: Mensagem explicativa associada ao estado.

        Returns:
            Dicionário serializável contendo lobby e jogo.
        """
        return serialize_game_state(self.game, self.lobby.get_players(), message)

    # -------------------------------------------------------------------------
    # Gerenciamento de Sala e Jogadores (Lobby)
    # -------------------------------------------------------------------------

    def register_player(self, player_name: str, callback_uri: str) -> dict[str, Any]:
        """Registra um novo jogador no lobby da partida.

        Args:
            player_name: Nome do jogador.
            callback_uri: URI de conexão Pyro5 do Daemon do cliente para callbacks.

        Returns:
            Dicionário com 'player_id', 'name' e 'game_state'.

        Raises:
            ValueError: Se o nome for vazio, URI inválida, sala cheia ou jogo em andamento.
        """
        cleaned_name = (player_name or "").strip()
        if not cleaned_name:
            raise ValueError("O nome do jogador não pode ser vazio.")
        if not callback_uri:
            raise ValueError("URI de callback obrigatória para conexão bidirecional.")

        with self.lock:
            # 1. Se não há jogadores conectados, reseta qualquer resíduo de jogo anterior
            if not self.lobby.has_active_callbacks():
                if self.game is not None:
                    logger.info(
                        "Nenhum jogador conectado no servidor. Resetando estado do jogo para o lobby."
                    )
                    self.game = None

            # 2. Se a partida anterior já terminou com vencedor, reseta para o lobby
            elif self.game is not None and self.game.winner is not None:
                logger.info(
                    "Partida anterior já finalizada com vencedor (P%d). "
                    "Resetando para o lobby para acomodar nova conexão.",
                    self.game.winner,
                )
                self.game = None
                id_updates = self.lobby.reorganize()
                for uri, new_id in id_updates:
                    self.broadcaster.notify_one(uri, "on_assigned_id", new_id)

            # 3. Se uma partida ainda estiver ativamente em andamento, impede nova entrada
            if (
                self.game is not None
                and self.game.game_started
                and self.game.winner is None
            ):
                raise ValueError("A partida já começou! Não é possível entrar agora.")

            player_info = self.lobby.register(cleaned_name, callback_uri)
            state = self._get_game_state_unlocked(f"{cleaned_name} entrou no lobby.")

        # Notifica todos os jogadores sobre a entrada
        self._broadcast("on_player_joined", player_info, state["lobby"])
        self._broadcast(
            "on_game_state_changed", state, f"{cleaned_name} entrou no lobby."
        )

        return {
            "player_id": player_info["id"],
            "name": cleaned_name,
            "game_state": state,
        }

    def unregister_player(self, player_id: int) -> tuple[bool, str]:
        """Desconecta um jogador do servidor de forma graciosa.

        Se a partida estiver em andamento, elimina o jogador e pode declarar vitória por W.O.
        Se ainda estiver no lobby, reorganiza os IDs restantes sequencialmente.

        Args:
            player_id: ID do jogador solicitante da desconexão.

        Returns:
            Tupla (sucesso, mensagem_status).
        """
        game_over_event: tuple[int, str, dict[str, Any]] | None = None

        with self.lock:
            found, removed_name = self.lobby.unregister(player_id)

            in_game = (
                self.game is not None
                and self.game.game_started
                and player_id in self.game.players
            )

            if not found and not in_game:
                return False, f"Jogador {player_id} não encontrado."

            if in_game:
                p = self.game.players[player_id]
                if p.is_active and self.game.winner is None:
                    state, msg, is_over = self._eliminate_player_unlocked(
                        player_id, "desconectou da partida"
                    )
                    if is_over and self.game.winner:
                        winner = self.game.winner
                        winner_name = self.game.players[winner].name
                        game_over_event = (winner, winner_name, state)
                else:
                    msg = f"Jogador {removed_name or player_id} desconectou."
                    state = self._get_game_state_unlocked(msg)
            else:
                id_updates = self.lobby.reorganize()
                for uri, new_id in id_updates:
                    self.broadcaster.notify_one(uri, "on_assigned_id", new_id)
                msg = f"Jogador {removed_name} saiu do lobby."
                logger.info(msg)
                state = self._get_game_state_unlocked(msg)

            # Se todos os jogadores saíram do servidor, reseta completamente
            if not self.lobby.has_active_callbacks():
                logger.info(
                    "Todos os jogadores saíram. Servidor reiniciado para o estado inicial de espera."
                )
                self.game = None
                self.lobby.clear()
                return True, msg

        if game_over_event:
            self._broadcast("on_game_over", *game_over_event)
        self._broadcast("on_player_left", player_id, state["lobby"])
        self._broadcast("on_game_state_changed", state, msg)
        return True, msg

    def start_game(self, player_id: int | None = None) -> tuple[bool, str]:
        """Inicia a partida de Quoridor no servidor quando há 2 ou 4 jogadores no lobby.

        Args:
            player_id: ID opcional do jogador que solicitou o início.

        Returns:
            Tupla (sucesso, mensagem_resultado).
        """
        with self.lock:
            if (
                self.game is not None
                and self.game.game_started
                and self.game.winner is None
            ):
                return False, "A partida já está em andamento!"

            num_players = self.lobby.count()
            if num_players not in ALLOWED_PLAYER_COUNTS:
                msg = (
                    f"A partida só pode ser iniciada com 2 ou 4 jogadores! "
                    f"Atualmente há {num_players} jogador(es) no lobby."
                )
                logger.warning(msg)
                return False, msg

            players = self.lobby.get_players()
            self.game = QuoridorGame(num_players=num_players)
            for p in players:
                assigned_id = self.game.add_player(p["name"])
                logger.debug(
                    "Jogador '%s' vinculado ao ID de jogo %d", p["name"], assigned_id
                )

            logger.info("Partida iniciada com sucesso com %d jogadores!", num_players)
            state = self._get_game_state_unlocked("A partida foi iniciada!")

        # Notifica todos os clientes via broadcast
        self._broadcast("on_game_started", state)
        self._broadcast(
            "on_game_state_changed", state, "Partida iniciada! Vez do Jogador 1."
        )
        return True, f"Partida iniciada com {num_players} jogadores!"

    # -------------------------------------------------------------------------
    # Ações de Jogo (Movimentação e Paredes)
    # -------------------------------------------------------------------------

    def move_player(
        self, player_id: int, new_position: tuple[int, int] | list[int]
    ) -> tuple[bool, str]:
        """Executa a movimentação do peão de um jogador no tabuleiro compartilhado.

        Args:
            player_id: ID do jogador que realiza a jogada.
            new_position: Coordenadas (linha, coluna) de destino.

        Returns:
            Tupla (sucesso, mensagem_resultado).
        """
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

        if winner:
            logger.info("Fim de jogo! Jogador %d (%s) venceu!", winner, winner_name)
            self._broadcast("on_game_over", winner, winner_name, state)
            self._broadcast(
                "on_game_state_changed", state, f"Vitória de {winner_name}!"
            )
        else:
            turn_msg = (
                f"{p_name} moveu para {target_pos}. Vez do Jogador {current_turn}."
            )
            self._broadcast("on_game_state_changed", state, turn_msg)

        return True, msg

    def place_wall(
        self, player_id: int, position: tuple[int, int] | list[int], orientation: str
    ) -> tuple[bool, str]:
        """Posiciona uma parede no tabuleiro compartilhado para o jogador.

        Args:
            player_id: ID do jogador que coloca a barreira.
            position: Posição de ancoragem (0-7, 0-7).
            orientation: Orientação ('H' para horizontal, 'V' para vertical).

        Returns:
            Tupla (sucesso, mensagem_resultado).
        """
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
    # Consultas de Estado e Utilidades
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
            wall = Wall(
                position=(int(position[0]), int(position[1])),
                orientation=orientation.strip().upper(),
            )
            return self.game.can_place_wall(player_id, wall)

    def reset_game(self, player_id: int | None = None) -> tuple[bool, str]:
        """Reinicia o jogo, retornando ao lobby apenas com os jogadores conectados mantidos."""
        with self.lock:
            self.game = None
            id_updates = self.lobby.reorganize()
            for uri, new_id in id_updates:
                self.broadcaster.notify_one(uri, "on_assigned_id", new_id)
            msg = "A partida foi reiniciada para o lobby."
            state = self._get_game_state_unlocked(msg)

        logger.info(msg)
        self._broadcast("on_game_state_changed", state, msg)
        return True, msg

    def ping(self) -> bool:
        """Verificação rápida de disponibilidade do servidor (heartbeat).

        Returns:
            True se o servidor estiver operacional.
        """
        return True


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
    """Inicializa o servidor Pyro5, registra no Name Server e inicia o atendimento.

    Args:
        server_name: Nome do serviço no Name Server (padrão: 'quoridor.servidor').
        host: Interface de rede para o Daemon do servidor.
        port: Porta para o Daemon (0 para seleção automática).
        ns_host: Endereço do Name Server Pyro5.
        ns_port: Porta do Name Server Pyro5.
        auto_start_ns: Se True, inicia automaticamente um Name Server embutido caso necessário.

    Returns:
        Tupla (daemon_pyro, instancia_servidor, thread_name_server_opcional).
    """
    configure_pyro()
    from Pyro5.api import config

    if ns_host:
        config.NS_HOST = ns_host
    if ns_port:
        config.NS_PORT = ns_port

    ns_thread: threading.Thread | None = None

    try:
        ns = Pyro5.api.locate_ns(host=ns_host, port=ns_port)
        logger.info(
            "Name Server do Pyro5 localizado com sucesso em %s:%s", ns_host, ns_port
        )
    except Pyro5.errors.NamingError:
        if auto_start_ns:
            logger.info(
                "Name Server não encontrado. Iniciando Name Server embutido em %s:%s...",
                ns_host,
                ns_port,
            )
            ns_thread = threading.Thread(
                target=Pyro5.api.start_ns_loop,
                kwargs={"host": ns_host, "port": ns_port},
                daemon=True,
                name="EmbeddedNameServerThread",
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

    daemon = Pyro5.api.Daemon(host=host, port=port)
    server_instance = QuoridorServer()
    server_uri = daemon.register(server_instance)

    ns.register(server_name, server_uri)

    logger.info("=" * 60)
    logger.info("Servidor Quoridor publicado com sucesso!")
    logger.info("Nome amigável no Name Server: PYRONAME:%s", server_name)
    logger.info("URI direta Pyro: %s", server_uri)
    logger.info("=" * 60)

    return daemon, server_instance, ns_thread
