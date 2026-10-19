from __future__ import annotations

from typing import Any

from network.config import MAX_PLAYERS, logger


class LobbyManager:
    """Gerencia a sala de espera (lobby), lista de jogadores e mapeamento de callbacks.

    Responsabilidades:
    - Validação e registro de novos jogadores.
    - Alocação e reordenação sequencial de IDs de 1 a N.
    - Sincronização e purga de conexões órfãs ou inativas.
    """

    def __init__(self, max_players: int = MAX_PLAYERS) -> None:
        """Inicializa um lobby vazio.

        Args:
            max_players: Limite máximo de jogadores permitidos simultaneamente na sala.
        """
        self.max_players = max_players
        self.players: list[dict[str, Any]] = []
        self.callbacks: dict[int, str] = {}

    def register(self, player_name: str, callback_uri: str) -> dict[str, Any]:
        """Registra um novo jogador no lobby e aloca seu identificador numérico.

        Args:
            player_name: Nome informado pelo jogador.
            callback_uri: Endereço do Daemon Pyro5 do cliente para callbacks.

        Returns:
            Dicionário contendo os dados do jogador registrado ('id', 'name', 'callback_uri').

        Raises:
            ValueError: Se o nome ou URI forem vazios, ou se a sala estiver cheia.
        """
        cleaned_name = (player_name or "").strip()
        if not cleaned_name:
            raise ValueError("O nome do jogador não pode ser vazio.")
        if not callback_uri:
            raise ValueError("URI de callback obrigatória para conexão bidirecional.")

        # Purga do lobby qualquer entrada órfã antes de verificar lotação
        self.players = [p for p in self.players if p["id"] in self.callbacks]

        if len(self.players) >= self.max_players:
            raise ValueError(
                f"O lobby está cheio! Limite máximo de {self.max_players} jogadores atingido."
            )

        existing_ids = {p["id"] for p in self.players}
        new_id = next(
            i for i in range(1, self.max_players + 1) if i not in existing_ids
        )

        player_info = {
            "id": new_id,
            "name": cleaned_name,
            "callback_uri": callback_uri,
        }
        self.players.append(player_info)
        self.players.sort(key=lambda p: p["id"])
        self.callbacks[new_id] = callback_uri

        logger.info(
            "Jogador registrado no lobby: ID %d, Nome '%s'. Total: %d/%d",
            new_id,
            cleaned_name,
            len(self.players),
            self.max_players,
        )
        return player_info

    def unregister(self, player_id: int) -> tuple[bool, str]:
        """Remove um jogador do lobby e de seus callbacks ativos.

        Args:
            player_id: ID do jogador a ser removido.

        Returns:
            Tupla (encontrado, nome_removido).
        """
        removed_name = ""
        found = False
        for p in self.players:
            if p["id"] == player_id:
                found = True
                removed_name = p["name"]
                break

        if player_id in self.callbacks:
            del self.callbacks[player_id]

        self.players = [p for p in self.players if p["id"] != player_id]
        return found, removed_name

    def remove(self, player_id: int) -> None:
        """Remove o jogador do lobby e dos callbacks caso exista.

        Args:
            player_id: ID do jogador a ser excluído.
        """
        if player_id in self.callbacks:
            del self.callbacks[player_id]
        self.players = [p for p in self.players if p["id"] != player_id]

    def reorganize(self) -> list[tuple[str, int]]:
        """Purga entradas sem callback ativo e renumera sequencialmente os IDs de 1 a N.

        Garante consistência na sala de espera após desconexões, retornando
        a lista de atualizações necessárias para notificar os clientes afetados.

        Returns:
            Lista de tuplas (callback_uri, novo_id) para jogadores cujo ID foi alterado.
        """
        self.players = [p for p in self.players if p["id"] in self.callbacks]
        old_callbacks = dict(self.callbacks)
        self.callbacks.clear()

        id_updates: list[tuple[str, int]] = []
        for idx, p in enumerate(self.players, start=1):
            old_id = p["id"]
            p["id"] = idx
            if old_id in old_callbacks:
                self.callbacks[idx] = old_callbacks[old_id]
                if old_id != idx:
                    id_updates.append((old_callbacks[old_id], idx))

        return id_updates

    def clear(self) -> None:
        """Limpa completamente todos os jogadores e callbacks registrados."""
        self.players.clear()
        self.callbacks.clear()

    def has_active_callbacks(self) -> bool:
        """Verifica se ainda existe algum cliente conectado com callback registrado.

        Returns:
            True se houver ao menos 1 callback ativo.
        """
        return len(self.callbacks) > 0

    def count(self) -> int:
        """Retorna a quantidade atual de jogadores no lobby.

        Returns:
            Número inteiro de jogadores presentes.
        """
        return len(self.players)

    def is_full(self) -> bool:
        """Verifica se o lobby atingiu o limite de participantes.

        Returns:
            True se a sala estiver cheia.
        """
        return len(self.players) >= self.max_players

    def get_callbacks_snapshot(self) -> list[tuple[int, str]]:
        """Retorna uma cópia snapshot da lista de callbacks atuais para broadcast.

        Returns:
            Lista de tuplas (player_id, callback_uri).
        """
        return list(self.callbacks.items())

    def get_players(self) -> list[dict[str, Any]]:
        """Retorna uma cópia da lista de dicionários dos jogadores do lobby.

        Returns:
            Lista de jogadores ordenados por ID.
        """
        return list(self.players)

    def get_player_name(self, player_id: int) -> str:
        """Obtém o nome associado a um ID no lobby ou um nome padrão formatado.

        Args:
            player_id: Identificador a ser consultado.

        Returns:
            Nome cadastrado ou 'Jogador {player_id}'.
        """
        for p in self.players:
            if p["id"] == player_id:
                return p["name"]
        return f"Jogador {player_id}"
