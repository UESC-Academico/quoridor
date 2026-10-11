"""Camada de rede (network) para Quoridor Multiplayer baseada em Pyro5."""

from network.config import (
    DEFAULT_NS_HOST,
    DEFAULT_NS_PORT,
    DEFAULT_SERVER_NAME,
    MAX_PLAYERS,
    MIN_PLAYERS,
    ALLOWED_PLAYER_COUNTS,
    configure_pyro,
)
from network.protocol import serialize_game_state, sync_game_from_state
from network.server import QuoridorServer, start_server
from network.client import QuoridorClient, GameClientCallback

__all__ = [
    "DEFAULT_NS_HOST",
    "DEFAULT_NS_PORT",
    "DEFAULT_SERVER_NAME",
    "MAX_PLAYERS",
    "MIN_PLAYERS",
    "ALLOWED_PLAYER_COUNTS",
    "configure_pyro",
    "serialize_game_state",
    "sync_game_from_state",
    "QuoridorServer",
    "start_server",
    "QuoridorClient",
    "GameClientCallback",
]
