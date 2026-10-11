import logging
import Pyro5.api
import Pyro5.serializers
from core.models import Player, Wall

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
)
logger = logging.getLogger("quoridor.network")

# Network defaults
DEFAULT_SERVER_NAME = "quoridor.servidor"
DEFAULT_NS_HOST = "localhost"
DEFAULT_NS_PORT = 9090
MAX_PLAYERS = 4
MIN_PLAYERS = 2
ALLOWED_PLAYER_COUNTS = (2, 4)

_pyro_configured = False


def configure_pyro() -> None:
    """Configura o ambiente Pyro5, definindo o serializador serpent e

    registrando serializers customizados para os dataclasses Wall e Player.
    """
    global _pyro_configured
    if _pyro_configured:
        return

    # Serialização do Wall
    Pyro5.api.register_class_to_dict(
        Wall,
        lambda w: {
            "__class__": "core.models.Wall",
            "position": tuple(w.position),
            "orientation": w.orientation,
        },
    )
    Pyro5.api.register_dict_to_class(
        "core.models.Wall",
        lambda _cn, d: Wall(tuple(d["position"]), d["orientation"]),
    )

    # Serialização do Player
    Pyro5.api.register_class_to_dict(
        Player,
        lambda p: {
            "__class__": "core.models.Player",
            "id": p.id,
            "name": p.name,
            "position": tuple(p.position),
            "target_axis": p.target_axis,
            "target_value": p.target_value,
            "remaining_walls": p.remaining_walls,
        },
    )
    Pyro5.api.register_dict_to_class(
        "core.models.Player",
        lambda _cn, d: Player(
            id=d["id"],
            name=d["name"],
            position=tuple(d["position"]),
            target_axis=d["target_axis"],
            target_value=d["target_value"],
            remaining_walls=d["remaining_walls"],
        ),
    )

    _pyro_configured = True
    logger.debug("Pyro5 configurado com sucesso para Quoridor.")
