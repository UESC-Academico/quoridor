"""Camada de rede (network) para Quoridor Multiplayer baseada em Pyro5."""

from network.client import GameClientCallback, QuoridorClient
from network.config import (
    ALLOWED_PLAYER_COUNTS,
    DEFAULT_NS_HOST,
    DEFAULT_NS_PORT,
    DEFAULT_SERVER_NAME,
    MAX_PLAYERS,
    MIN_PLAYERS,
    configure_pyro,
)
from network.protocol import serialize_game_state, sync_game_from_state
from network.server import QuoridorServer, start_server

__all__ = [
    "ALLOWED_PLAYER_COUNTS",
    "DEFAULT_NS_HOST",
    "DEFAULT_NS_PORT",
    "DEFAULT_SERVER_NAME",
    "MAX_PLAYERS",
    "MIN_PLAYERS",
    "GameClientCallback",
    "QuoridorClient",
    "QuoridorServer",
    "configure_pyro",
    "serialize_game_state",
    "start_server",
    "sync_game_from_state",
]
