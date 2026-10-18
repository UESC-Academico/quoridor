import logging

import Pyro5.api
import Pyro5.serializers

from core.models import Player, Wall

# Configurações de logging do subsistema de rede
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
)
logger = logging.getLogger("quoridor.network")

# Constantes de configuração do Pyro5 e regras de rede
DEFAULT_SERVER_NAME = (
    "quoridor.servidor"  # Nome amigável registrado no Name Server (pyro5-ns)
)
DEFAULT_NS_HOST = "localhost"  # Host padrão do Pyro5 Name Server
DEFAULT_NS_PORT = 9090  # Porta padrão do Pyro5 Name Server
MAX_PLAYERS = 4  # Capacidade máxima da sala de jogo
MIN_PLAYERS = 2  # Mínimo de jogadores necessários para início da partida
ALLOWED_PLAYER_COUNTS = (2, 4)  # Quantidades permitidas de jogadores para início legal

_pyro_configured = False


def configure_pyro() -> None:
    """Configura o ambiente Pyro5 e os serializadores serpent customizados.

    Garante idempotência (executa apenas uma vez). Registra funções bidirecionais
    de serialização e desserialização entre dataclasses (`Wall` e `Player`) e dicionários,
    permitindo tráfego seguro de dados estruturados pela rede.
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
