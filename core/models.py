from dataclasses import dataclass


@dataclass(frozen=True)
class Wall:
    """Representa uma parede colocada no tabuleiro do Quoridor.

    Atributos:
        position: Coordenadas (linha, coluna) de 0 a 7 que definem o ponto de
            ancoragem superior/esquerdo da barreira.
        orientation: Orientação da parede ('H' para horizontal, 'V' para vertical).
            Cada parede tem o comprimento de 2 células e ocupa a ranhura entre elas.
    """

    position: tuple[int, int]
    orientation: str


@dataclass
class Player:
    """Representa um jogador na partida.

    Atributos:
        id: Identificador numérico do jogador (1 a 4).
        name: Nome de exibição do jogador.
        position: Posição atual do peão no tabuleiro como (linha, coluna) de 0 a 8.
        target_axis: Eixo de vitória (0 para linha/horizontal, 1 para coluna/vertical).
        target_value: Índice da linha ou coluna meta que o peão deve atingir para vencer.
        remaining_walls: Quantidade de paredes ainda disponíveis para colocação.
        is_active: Indica se o jogador continua ativo na partida ou se foi eliminado/desconectado.
    """

    id: int
    name: str
    position: tuple[int, int]
    target_axis: int
    target_value: int
    remaining_walls: int
    is_active: bool = True
