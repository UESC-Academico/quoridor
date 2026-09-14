from collections import deque
from core.models import Wall

def has_path_to_goal(start_pos: tuple[int, int], 
                      target_axis: int, 
                      target_val: int, 
                      board) -> bool:

    queue = deque([start_pos])
    visited = {start_pos}

    while queue:
        current = queue.popleft()

        if current[target_axis] == target_val:
            return True

        r, c = current
        neighbors = [(r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)]

        for nr, nc in neighbors:
            neighbor = (nr, nc)

            if 0 <= nr < 9 and 0 <= nc < 9 and neighbor not in visited:

                if not board.is_path_blocked(current, neighbor):
                    visited.add(neighbor)
                    queue.append(neighbor)

    return False  