import sys
import pygame
from core.game import QuoridorGame
from core.models import Wall

from ui.constants import *
from ui.utils import draw_smooth_circle

class QuoridorGUI:
    def __init__(self, num_players: int = 2):
        pygame.init()

        # 1. Setup Window
        info = pygame.display.Info()
        initial_w = int(info.current_w * 0.90)
        initial_h = int(info.current_h * 0.88)
        self.screen = pygame.display.set_mode((initial_w, initial_h))
        pygame.display.set_caption("Quoridor")
        self.clock = pygame.time.Clock()

        # Current dimensions after maximize
        current_w, current_h = self.screen.get_size()
        self.update_dimensions(current_w, current_h)

        # Core Game Instance
        self.game = QuoridorGame(num_players=num_players)
        for i in range(1, num_players + 1):
            self.game.add_player(f"Jogador {i}")

        self.num_players = num_players
        # GUI State
        self.input_mode: str = 'PAWN' # 'PAWN' or 'WALL'
        self.wall_orientation: str = 'H'  # 'H' or 'V'
        self.status_message: str = "Pressione SPACE para habilitar posicionamento de parede"
        self.status_color = (200, 205, 220)
        self.error_message_time = 0

    def reset_game(self) -> None:
        self.game = QuoridorGame(num_players=self.num_players)
        for i in range(1, self.num_players + 1):
            self.game.add_player(f"Jogador {i}")
        self.status_message = "Pressione SPACE para habilitar posicionamento de parede"
        self.input_mode = 'PAWN'
        self.wall_orientation = 'H'
        self.error_message_time = 0

    def update_dimensions(self, width: int, height: int) -> None:
        """Dynamically recalculates all board and font dimensions upon window resize."""
        self.screen_width = width
        self.screen_height = height

        board_max_height = int(self.screen_height * 0.74)
        board_max_width = int(self.screen_width * 0.55)
        target_size = min(board_max_height, board_max_width)

        self.cell_size = max(24, int(target_size / 10.8))
        self.groove_size = max(6, int(self.cell_size * 0.22))
        self.board_size = 9 * self.cell_size + 8 * self.groove_size

        self.offset_x = (self.screen_width - self.board_size) // 2
        self.offset_y = (self.screen_height - self.board_size) // 2 - 20

        # Responsive Fonts
        self.font_title = pygame.font.SysFont("arial", max(16, int(self.cell_size * 0.46)), bold=True)
        self.font_card_name = pygame.font.SysFont("arial", max(14, int(self.cell_size * 0.36)), bold=True)
        self.font_hud = pygame.font.SysFont("arial", max(12, int(self.cell_size * 0.28)), bold=True)
        self.font_pawn = pygame.font.SysFont("arial", max(13, int(self.cell_size * 0.36)), bold=True)
        self.font_small = pygame.font.SysFont("arial", max(10, int(self.cell_size * 0.24)))

    def get_cell_rect(self, row: int, col: int) -> pygame.Rect:
        """Calculates pixel rectangle for a cell (row, col)."""
        x = self.offset_x + col * (self.cell_size + self.groove_size)
        y = self.offset_y + row * (self.cell_size + self.groove_size)
        return pygame.Rect(x, y, self.cell_size, self.cell_size)

    def get_wall_rect(self, row: int, col: int, orientation: str) -> pygame.Rect:
        """Calculates pixel rectangle for a wall spanning 2 squares."""
        x = self.offset_x + col * (self.cell_size + self.groove_size)
        y = self.offset_y + row * (self.cell_size + self.groove_size)

        if orientation == 'H':
            wall_x = x
            wall_y = y + self.cell_size
            wall_width = 2 * self.cell_size + self.groove_size
            wall_height = self.groove_size
        else:  # 'V'
            wall_x = x + self.cell_size
            wall_y = y
            wall_width = self.groove_size
            wall_height = 2 * self.cell_size + self.groove_size

        return pygame.Rect(wall_x, wall_y, wall_width, wall_height)

    def get_hovered_cell(self, mouse_pos: tuple[int, int]) -> tuple[int, int] | None:
        """Detects if mouse is inside one of the 81 cells."""
        mx, my = mouse_pos
        for r in range(9):
            for c in range(9):
                if self.get_cell_rect(r, c).collidepoint(mx, my):
                    return (r, c)
        return None

    def get_hovered_wall_slot(self, mouse_pos: tuple[int, int]) -> tuple[int, int] | None:
        """Finds closest wall intersection (0-7, 0-7) to mouse cursor."""
        mx, my = mouse_pos
        threshold = self.cell_size // 2 + self.groove_size

        for r in range(8):
            for c in range(8):
                center_x = self.offset_x + c * (self.cell_size + self.groove_size) + self.cell_size + self.groove_size // 2
                center_y = self.offset_y + r * (self.cell_size + self.groove_size) + self.cell_size + self.groove_size // 2

                distance = ((mx - center_x) ** 2 + (my - center_y) ** 2) ** 0.5
                if distance <= threshold:
                    return (r, c)
        return None

    def draw_player_card(self, player, rect: pygame.Rect) -> None:
        """Renders player card with centered wall count bars."""
        is_turn = (self.game.turn == player.id and not self.game.winner)
        color = PLAYER_COLORS.get(player.id, (255, 255, 255))
        border_color = color if is_turn else CARD_BORDER_INACTIVE
        border_width = 3 if is_turn else 1

        # Card Frame
        pygame.draw.rect(self.screen, CARD_BG_COLOR, rect, border_radius=12)
        pygame.draw.rect(self.screen, border_color, rect, width=border_width, border_radius=12)

        # Avatar
        avatar_radius = max(14, int(self.cell_size * 0.32))
        avatar_center = (rect.x + avatar_radius + 18, rect.y + avatar_radius + 18)
        draw_smooth_circle(self.screen, avatar_center, avatar_radius, color, border_color=(15, 17, 22), border_width=2)
        avatar_label = self.font_hud.render(f"P{player.id}", True, (15, 17, 22))
        self.screen.blit(avatar_label, avatar_label.get_rect(center=avatar_center))

        # Name
        name_surf = self.font_card_name.render(player.name, True, (240, 242, 250))
        self.screen.blit(name_surf, (avatar_center[0] + avatar_radius + 16, rect.y + 20))

        # Turn Indicator Tag
        status_str = "SUA VEZ" if is_turn else "AGUARDANDO"
        status_color = color if is_turn else (120, 125, 145)
        status_surf = self.font_small.render(status_str, True, status_color)
        self.screen.blit(status_surf, (avatar_center[0] + avatar_radius + 16, rect.y + 52))

        # Divider
        divider_y = rect.y + int(rect.height * 0.50)
        pygame.draw.line(self.screen, (45, 48, 62), (rect.x + 18, divider_y), (rect.right - 18, divider_y), 1)

        # Centered Wall Text
        walls_text = f"Paredes: {player.remaining_walls} / {self.game.walls_per_player}"
        walls_surf = self.font_hud.render(walls_text, True, (210, 215, 230))
        self.screen.blit(walls_surf, (rect.x + (rect.width - walls_surf.get_width()) // 2, divider_y + 12))

        # Centered Wall Count Blocks
        block_w = max(10, int(self.cell_size * 0.22))
        block_h = max(12, int(self.cell_size * 0.26))
        gap = max(3, int(self.cell_size * 0.06))
        total_blocks_w = self.game.walls_per_player * block_w + (self.game.walls_per_player - 1) * gap
        start_x = rect.x + (rect.width - total_blocks_w) // 2
        bar_y = divider_y + 40

        for i in range(self.game.walls_per_player):
            block_color = color if i < player.remaining_walls else (45, 48, 62)
            pygame.draw.rect(self.screen, block_color, (start_x, bar_y, block_w, block_h), border_radius=2)
            start_x += block_w + gap

    def draw_sidebars(self) -> None:
        """Renders lateral sidebars for 2 or 4 players."""
        side_width = min(320, max(180, self.offset_x - 50))
        left_x = (self.offset_x - side_width) // 2
        right_x = self.offset_x + self.board_size + (self.offset_x - side_width) // 2
        card_height = max(150, int(self.board_size * 0.28))

        if self.game.num_players == 2:
            center_y = self.offset_y + (self.board_size - card_height) // 2
            self.draw_player_card(self.game.players[1], pygame.Rect(left_x, center_y, side_width, card_height))
            self.draw_player_card(self.game.players[2], pygame.Rect(right_x, center_y, side_width, card_height))

        elif self.game.num_players == 4:
            gap = 18
            total_h = 2 * card_height + gap
            start_y = self.offset_y + (self.board_size - total_h) // 2

            self.draw_player_card(self.game.players[1], pygame.Rect(left_x, start_y, side_width, card_height))
            self.draw_player_card(self.game.players[3], pygame.Rect(left_x, start_y + card_height + gap, side_width, card_height))

            self.draw_player_card(self.game.players[2], pygame.Rect(right_x, start_y, side_width, card_height))
            self.draw_player_card(self.game.players[4], pygame.Rect(right_x, start_y + card_height + gap, side_width, card_height))

    def draw_target_goal_edge(self) -> None:
        """Highlights the active player's target baseline edge with their color."""
        if self.game.winner:
            return

        current = self.game.players[self.game.turn]
        color = PLAYER_COLORS.get(current.id, (255, 255, 255))
        edge_thickness = max(4, int(self.groove_size * 0.55))

        if current.target_axis == 0:
            if current.target_value == 8:
                # Bottom Edge (P1)
                y = self.offset_y + self.board_size + 4
                pygame.draw.rect(self.screen, color, (self.offset_x, y, self.board_size, edge_thickness), border_radius=3)
            elif current.target_value == 0:
                # Top Edge (P2)
                y = self.offset_y - edge_thickness - 4
                pygame.draw.rect(self.screen, color, (self.offset_x, y, self.board_size, edge_thickness), border_radius=3)
        elif current.target_axis == 1:
            if current.target_value == 8:
                # Right Edge (P3)
                x = self.offset_x + self.board_size + 4
                pygame.draw.rect(self.screen, color, (x, self.offset_y, edge_thickness, self.board_size), border_radius=3)
            elif current.target_value == 0:
                # Left Edge (P4)
                x = self.offset_x - edge_thickness - 4
                pygame.draw.rect(self.screen, color, (x, self.offset_y, edge_thickness, self.board_size), border_radius=3)

    def draw_board(self, mouse_pos: tuple[int, int]) -> None:
        """Renders board, cells, pawns, walls, and the active goal edge."""
        board_rect = pygame.Rect(self.offset_x - 12, self.offset_y - 12, self.board_size + 24, self.board_size + 24)
        pygame.draw.rect(self.screen, BOARD_BG_COLOR, board_rect, border_radius=10)

        # Highlight Goal Edge
        self.draw_target_goal_edge()

        current_player = self.game.players[self.game.turn]
        current_color = PLAYER_COLORS.get(current_player.id, (255, 255, 255))
        valid_moves = self.game.get_valid_moves(current_player.id) if not self.game.winner else []
        hovered_cell = self.get_hovered_cell(mouse_pos)

        # 1. Cells
        for r in range(9):
            for c in range(9):
                rect = self.get_cell_rect(r, c)
                color = CELL_HOVER_COLOR if (r, c) == hovered_cell else CELL_COLOR
                pygame.draw.rect(self.screen, color, rect, border_radius=6)

                # Valid Move Projection
                if (r, c) in valid_moves:
                    draw_smooth_circle(self.screen, rect.center, int(self.cell_size * 0.22), (*current_color, 150))
                    draw_smooth_circle(self.screen, rect.center, int(self.cell_size * 0.10), current_color)

        # 2. Placed Walls
        for wall in self.game.walls:
            r, c = wall.position
            wall_rect = self.get_wall_rect(r, c, wall.orientation)
            pygame.draw.rect(self.screen, WALL_COLOR, wall_rect, border_radius=4)

        # 3. Ghost Wall Hover
        hovered_wall_slot = self.get_hovered_wall_slot(mouse_pos)
        if self.input_mode == 'WALL' and hovered_wall_slot and not self.game.winner and current_player.remaining_walls > 0:
            hr, hc = hovered_wall_slot
            preview_wall = Wall((hr, hc), self.wall_orientation)
            can_place, _ = self.game.can_place_wall(current_player.id, preview_wall)

            ghost_color = GHOST_VALID_COLOR if can_place else GHOST_INVALID_COLOR
            ghost_rect = self.get_wall_rect(hr, hc, self.wall_orientation)

            ghost_surface = pygame.Surface((ghost_rect.width, ghost_rect.height), pygame.SRCALPHA)
            ghost_surface.fill(ghost_color)
            self.screen.blit(ghost_surface, ghost_rect.topleft)

        # 4. Pawns
        for player in self.game.players.values():
            r, c = player.position
            center = self.get_cell_rect(r, c).center
            color = PLAYER_COLORS.get(player.id, (255, 255, 255))
            radius = self.cell_size // 2 - 8

            draw_smooth_circle(self.screen, center, radius, color, border_color=(15, 17, 22), border_width=3)
            label_surf = self.font_pawn.render(f"P{player.id}", True, (15, 17, 22))
            self.screen.blit(label_surf, label_surf.get_rect(center=center))

    def draw_hud(self) -> None:
        """Renders centered turn header and victory announcement without quotes."""
        if self.game.winner:
            winner = self.game.players[self.game.winner]
            color = PLAYER_COLORS.get(winner.id, (255, 255, 255))
            win_text = f"{winner.name} venceu a partida!"
            win_surf = self.font_title.render(win_text, True, color)
            self.screen.blit(win_surf, (self.screen_width // 2 - win_surf.get_width() // 2, self.offset_y - 50))
            
            hint_text = "Pressione ENTER para jogar novamente"
            hint_surf = self.font_hud.render(hint_text, True, (200, 205, 220))
            self.screen.blit(hint_surf, (self.screen_width // 2 - hint_surf.get_width() // 2, self.offset_y + self.board_size + 24))
            return

        # Centered Turn Header: Vez de [nome]
        current = self.game.players[self.game.turn]
        current_color = PLAYER_COLORS.get(current.id, (255, 255, 255))
        turn_text = f"Vez de {current.name}"
        turn_surf = self.font_title.render(turn_text, True, current_color)
        self.screen.blit(turn_surf, (self.screen_width // 2 - turn_surf.get_width() // 2, self.offset_y - 50))

        # Centered Feedback Message (Bottom)
        if self.status_message:
            msg_surf = self.font_hud.render(self.status_message, True, self.status_color)
            self.screen.blit(msg_surf, (self.screen_width // 2 - msg_surf.get_width() // 2, self.offset_y + self.board_size + 24))

    def handle_mouse_click(self, mouse_pos: tuple[int, int]) -> None:
        """Processes mouse click to move pawn or place wall."""
        if self.game.winner:
            return

        current_player = self.game.players[self.game.turn]

        if self.input_mode == 'PAWN':
            # 1. Move Pawn
            clicked_cell = self.get_hovered_cell(mouse_pos)
            if clicked_cell:
                valid_moves = self.game.get_valid_moves(current_player.id)
                if clicked_cell in valid_moves:
                    success, msg = self.game.move_player(current_player.id, clicked_cell)
                    if success:
                        self.status_message = "Pressione SPACE para desabilitar posicionamento de parede" if self.input_mode == 'WALL' else "Pressione SPACE para habilitar posicionamento de parede"
                        self.status_color = (200, 205, 220)
                        self.error_message_time = 0
                    else:
                        self.status_message = msg
                        self.status_color = (230, 57, 70)
                        self.error_message_time = pygame.time.get_ticks()
        elif self.input_mode == 'WALL':
            # 2. Place Wall
            clicked_wall_slot = self.get_hovered_wall_slot(mouse_pos)
            if clicked_wall_slot:
                if current_player.remaining_walls <= 0:
                    self.status_message = "Voce nao tem mais paredes disponiveis!"
                    self.status_color = (230, 57, 70)
                    self.error_message_time = pygame.time.get_ticks()
                    return

                new_wall = Wall(clicked_wall_slot, self.wall_orientation)
                success, msg = self.game.place_wall(current_player.id, new_wall)
                if success:
                    self.status_message = "Pressione SPACE para desabilitar posicionamento de parede" if self.input_mode == 'WALL' else "Pressione SPACE para habilitar posicionamento de parede"
                    self.status_color = (200, 205, 220)
                    self.error_message_time = 0
                else:
                    self.status_message = msg
                    self.status_color = (230, 57, 70)
                    self.error_message_time = pygame.time.get_ticks()

    def run(self) -> None:
        """Main game event loop."""
        running = True
        while running:
            mouse_pos = pygame.mouse.get_pos()

            if self.error_message_time > 0 and pygame.time.get_ticks() - self.error_message_time > 3000:
                self.status_message = "Pressione SPACE para desabilitar posicionamento de parede" if self.input_mode == 'WALL' else "Pressione SPACE para habilitar posicionamento de parede"
                self.status_color = (200, 205, 220)
                self.error_message_time = 0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_r:
                        self.wall_orientation = 'V' if self.wall_orientation == 'H' else 'H'
                    elif event.key == pygame.K_SPACE:
                        self.input_mode = 'WALL' if self.input_mode == 'PAWN' else 'PAWN'
                        self.status_message = "Pressione SPACE para desabilitar posicionamento de parede" if self.input_mode == 'WALL' else "Pressione SPACE para habilitar posicionamento de parede"
                        self.status_color = (200, 205, 220)
                        self.error_message_time = 0
                    elif event.key == pygame.K_RETURN and self.game.winner:
                        self.reset_game()

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self.handle_mouse_click(mouse_pos)
                    elif event.button == 3:
                        self.wall_orientation = 'V' if self.wall_orientation == 'H' else 'H'

            self.screen.fill(BG_COLOR)
            self.draw_board(mouse_pos)
            self.draw_sidebars()
            self.draw_hud()

            pygame.display.flip()
            self.clock.tick(FPS)

        pygame.quit()
        sys.exit()
