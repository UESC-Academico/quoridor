from __future__ import annotations
from typing import Any
from core.models import Player, Wall
from core.game import QuoridorGame


def serialize_game_state(
    game: QuoridorGame | None,
    lobby_players: list[dict[str, Any]],
    status_message: str = ""
) -> dict[str, Any]:
    """Converte o estado do jogo e do lobby em um dicionário serializável para a rede."""
    state: dict[str, Any] = {
        "status_message": status_message,
        "lobby": [
            {
                "id": p["id"],
                "name": p["name"],
                "ready": p.get("ready", True),
            }
            for p in lobby_players
        ],
        "lobby_count": len(lobby_players),
        "can_start": len(lobby_players) in (2, 4) and (game is None or not game.game_started),
        "game_started": False,
        "num_players": 4 if len(lobby_players) > 2 else 2,
        "turn": 1,
        "winner": None,
        "players": {},
        "walls": [],
        "walls_per_player": 5 if len(lobby_players) > 2 else 10,
    }

    if game is not None and game.game_started:
        state["game_started"] = True
        state["num_players"] = game.num_players
        state["turn"] = game.turn
        state["winner"] = game.winner
        state["walls_per_player"] = game.walls_per_player
        state["players"] = {
            pid: {
                "id": p.id,
                "name": p.name,
                "position": tuple(p.position),
                "target_axis": p.target_axis,
                "target_value": p.target_value,
                "remaining_walls": p.remaining_walls,
            }
            for pid, p in game.players.items()
        }
        state["walls"] = [
            {
                "position": tuple(w.position),
                "orientation": w.orientation,
            }
            for w in game.walls
        ]

    return state


def sync_game_from_state(game: QuoridorGame, state: dict[str, Any]) -> None:
    """Sincroniza uma instância local de QuoridorGame a partir do dicionário de estado remoto."""
    game.num_players = state.get("num_players", game.num_players)
    game.turn = state.get("turn", 1)
    game.winner = state.get("winner", None)
    game.game_started = state.get("game_started", False)
    game.walls_per_player = state.get("walls_per_player", 10 if game.num_players == 2 else 5)

    # Atualiza jogadores
    game.players.clear()
    for pid_str, p_data in state.get("players", {}).items():
        pid = int(pid_str)
        game.players[pid] = Player(
            id=p_data["id"],
            name=p_data["name"],
            position=tuple(p_data["position"]),
            target_axis=p_data["target_axis"],
            target_value=p_data["target_value"],
            remaining_walls=p_data["remaining_walls"],
        )

    # Atualiza paredes
    game.walls.clear()
    for w_data in state.get("walls", []):
        if isinstance(w_data, Wall):
            game.walls.add(w_data)
        else:
            game.walls.add(Wall(
                position=tuple(w_data["position"]),
                orientation=w_data["orientation"],
            ))
