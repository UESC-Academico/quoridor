from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.game import QuoridorGame


def has_path_to_goal(
    start_pos: tuple[int, int], target_axis: int, target_val: int, board: QuoridorGame
) -> bool:
    """Verifica se existe pelo menos um caminho livre da posição inicial até a borda meta.

    Utiliza o algoritmo de Busca em Largura (BFS) para percorrer o grafo de células 9x9,
    respeitando as paredes presentes no tabuleiro.

    Args:
        start_pos: Coordenadas (linha, coluna) de partida do jogador.
        target_axis: Eixo de vitória a ser verificado (0 para linha, 1 para coluna).
        target_val: Valor da coordenada no eixo meta que encerra o caminho com vitória.
        board: Instância do jogo contendo o método `is_path_blocked` e o estado das paredes.

    Returns:
        True se existir ao menos uma trajetória viável até o objetivo; False caso contrário.
    """
    queue = deque([start_pos])
    visited = {start_pos}

    while queue:
        current = queue.popleft()

        # Verifica se o nó atual alcançou a linha/coluna objetivo
        if current[target_axis] == target_val:
            return True

        r, c = current
        neighbors = [(r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)]

        for nr, nc in neighbors:
            neighbor = (nr, nc)

            if (
                0 <= nr < 9
                and 0 <= nc < 9
                and neighbor not in visited
                and not board.is_path_blocked(current, neighbor)
            ):
                visited.add(neighbor)
                queue.append(neighbor)

    return False
