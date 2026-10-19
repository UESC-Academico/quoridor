from __future__ import annotations

from typing import TYPE_CHECKING, Any

import Pyro5.api

from network.config import logger

if TYPE_CHECKING:
    from network.client import QuoridorClient


@Pyro5.api.expose
class GameClientCallback:
    """Objeto remoto registrado no Daemon do cliente para receber notificações (callbacks) do servidor.

    Todos os métodos são decorados com @Pyro5.api.oneway para que o servidor não bloqueie sua
    execução aguardando respostas de rede.
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
        logger.info("ID do jogador atualizado pelo servidor para: %d", new_player_id)
        self.client.update_player_id(new_player_id)
