from core.models import Player, Wall
from core.pathfinding import has_path_to_goal


class QuoridorGame:
    PLAYER_CONFIG = (
        ((0, 4), 0, 8),
        ((8, 4), 0, 0),
        ((4, 0), 1, 8),
        ((4, 8), 1, 0),
    )

    def __init__(self, num_players: int = 2):

        if num_players not in (2, 4):
            raise ValueError("O Quoridor só suporta partidas de 2 ou 4 jogadores!")

        self.num_players: int = num_players
        self.players: dict[int, Player] = {}
        self.walls: set[Wall] = set()
        self.turn: int = 1
        self.winner: int | None = None
        self.game_started: bool = False
        self.walls_per_player: int = 10 if num_players == 2 else 5

    def add_player(self, name: str) -> int:
        if len(self.players) >= self.num_players:
            raise ValueError(
                f"Esta partida já atingiu o limite de {self.num_players} jogadores!"
            )

        if self.game_started:
            raise ValueError("O jogo já começou, novas entradas não são permitidas!")

        new_player_id = len(self.players) + 1

        init_position, axis, target = self.PLAYER_CONFIG[new_player_id - 1]

        self.players[new_player_id] = Player(
            id=new_player_id,
            name=name,
            position=init_position,
            target_axis=axis,
            target_value=target,
            remaining_walls=self.walls_per_player,
        )

        if len(self.players) == self.num_players:
            self.game_started = True

        return new_player_id

    def next_turn(self) -> None:
        active_ids = [pid for pid, p in sorted(self.players.items()) if p.is_active]
        if not active_ids:
            return
        if self.turn in active_ids:
            idx = active_ids.index(self.turn)
            self.turn = active_ids[(idx + 1) % len(active_ids)]
        else:
            higher = [pid for pid in active_ids if pid > self.turn]
            self.turn = higher[0] if higher else active_ids[0]

    def eliminate_player(self, player_id: int) -> int | None:
        """Elimina um jogador da partida (ex: por desconexão).

        Se restar apenas 1 jogador ativo, esse jogador é declarado vencedor imediato.
        Se o jogador eliminado era o jogador da vez, o turno passa para o próximo ativo.
        Retorna o ID do vencedor se a partida terminou, ou None se continua.
        """
        if player_id not in self.players:
            return self.winner

        player = self.players[player_id]
        if not player.is_active:
            return self.winner

        player.is_active = False

        active = [p for p in self.players.values() if p.is_active]

        # Se sobrou apenas 1 jogador, ele vence imediatamente!
        if len(active) == 1:
            self.winner = active[0].id
            return self.winner

        if len(active) == 0:
            return None

        # Se for a vez do jogador que saiu, avança para o próximo ativo
        if self.turn == player_id and not self.winner:
            self.next_turn()

        return self.winner

    def check_winner(self, player_id: int) -> bool:
        player = self.players[player_id]
        if player.position[player.target_axis] == player.target_value:
            self.winner = player_id
            return True
        return False

    def is_path_blocked(self, pos1: tuple[int, int], pos2: tuple[int, int]) -> bool:
        r1, c1 = pos1
        r2, c2 = pos2

        if c1 == c2:
            r_min = min(r1, r2)

            if Wall((r_min, c1), "H") in self.walls:
                return True
            if Wall((r_min, c1 - 1), "H") in self.walls:
                return True

        elif r1 == r2:
            c_min = min(c1, c2)

            if Wall((r1, c_min), "V") in self.walls:
                return True
            if Wall((r1 - 1, c_min), "V") in self.walls:
                return True

        return False

    def can_place_wall(self, player_id: int, wall: Wall) -> tuple[bool, str]:
        if not self.game_started:
            return False, "O jogo ainda não começou!"

        if self.turn != player_id:
            return False, "Não é a sua vez!"

        if player_id not in self.players or not self.players[player_id].is_active:
            return False, "Jogador não encontrado ou eliminado!"

        player = self.players[player_id]
        if player.remaining_walls <= 0:
            return False, "Você não tem mais paredes disponíveis!"

        r, c = wall.position
        if not (0 <= r < 8 and 0 <= c < 8):
            return False, "Posição da parede fora dos limites (0 a 7)!"

        if wall.orientation not in ("H", "V"):
            return False, "Orientação deve ser 'H' ou 'V'!"

        if wall in self.walls:
            return False, "Já existe uma parede nessa posição!"

        if wall.orientation == "H" and (
            Wall((r, c - 1), "H") in self.walls or Wall((r, c + 1), "H") in self.walls
        ):
            return False, "Sobreposição com parede horizontal existente!"
        elif wall.orientation == "V" and (
            Wall((r - 1, c), "V") in self.walls or Wall((r + 1, c), "V") in self.walls
        ):
            return False, "Sobreposição com parede vertical existente!"

        opposite = "V" if wall.orientation == "H" else "H"
        if Wall((r, c), opposite) in self.walls:
            return False, "Paredes não podem se cruzar em forma de cruz"

        self.walls.add(wall)

        clear_path = all(
            has_path_to_goal(p.position, p.target_axis, p.target_value, self)
            for p in self.players.values()
            if p.is_active
        )

        self.walls.remove(wall)

        if not clear_path:
            return False, "Jogada ilegal: esta parede tranca o caminho de um jogador!"

        return True, "Posição válida!"

    def place_wall(self, player_id: int, wall: Wall) -> tuple[bool, str]:
        valid, reason = self.can_place_wall(player_id, wall)
        if not valid:
            return False, reason

        self.walls.add(wall)
        self.players[player_id].remaining_walls -= 1
        self.next_turn()
        return True, "Parede colocada com sucesso!"

    def get_valid_moves(self, player_id: int) -> list[tuple[int, int]]:
        if player_id not in self.players or not self.players[player_id].is_active:
            return []
        current_pos = self.players[player_id].position
        r, c = current_pos

        occupied_positions = {
            p.position
            for p in self.players.values()
            if p.id != player_id and p.is_active
        }
        valid_moves = []

        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]

        for dr, dc in directions:
            neighbor = (r + dr, c + dc)
            nr, nc = neighbor

            if not (0 <= nr < 9 and 0 <= nc < 9):
                continue

            if self.is_path_blocked(current_pos, neighbor):
                continue

            if neighbor not in occupied_positions:
                valid_moves.append(neighbor)
            else:
                jump_straight = (r + 2 * dr, c + 2 * dc)
                jr, jc = jump_straight

                jump_straight_possible = (
                    0 <= jr < 9
                    and 0 <= jc < 9
                    and not self.is_path_blocked(neighbor, jump_straight)
                    and jump_straight not in occupied_positions
                )

                if jump_straight_possible:
                    valid_moves.append(jump_straight)
                else:
                    perpendicular = [(dc, dr), (-dc, -dr)]
                    for pdr, pdc in perpendicular:
                        diag = (nr + pdr, nc + pdc)
                        dr_diag, dc_diag = diag

                        if (
                            0 <= dr_diag < 9
                            and 0 <= dc_diag < 9
                            and not self.is_path_blocked(neighbor, diag)
                            and diag not in occupied_positions
                        ):
                            valid_moves.append(diag)

        return valid_moves

    def move_player(
        self, player_id: int, new_position: tuple[int, int]
    ) -> tuple[bool, str]:
        if not self.game_started:
            return False, "O jogo ainda não começou!"

        if player_id not in self.players or not self.players[player_id].is_active:
            return False, "Jogador não encontrado ou eliminado!"

        if self.turn != player_id:
            return False, "Não é a sua vez!"

        valid_moves = self.get_valid_moves(player_id)
        if new_position not in valid_moves:
            return False, f"Movimento inválido para {new_position}!"

        self.players[player_id].position = new_position

        if self.check_winner(player_id):
            return True, f"Parabéns! Jogador {player_id} venceu a partida!"

        self.next_turn()
        return True, "Movimento realizado com sucesso!"
