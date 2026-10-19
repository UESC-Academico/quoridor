from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pygame

from core.game import QuoridorGame
from core.models import Wall
from network.protocol import sync_game_from_state
from ui.constants import *
from ui.utils import draw_smooth_circle

if TYPE_CHECKING:
    from network.client import QuoridorClient


class QuoridorGUI:
    """Interface gráfica unificada do Quoridor (suporta modo local e multiplayer em rede)."""

    def __init__(
        self, num_players: int = 2, client: QuoridorClient | None = None
    ) -> None:
        """Inicializa a interface gráfica do Quoridor.

        Args:
            num_players: Quantidade de jogadores para partida local (2 ou 4).
                Ignorado quando um cliente de rede é fornecido.
            client: Instância de `QuoridorClient` para partidas online via Pyro5,
                ou None para jogo local no mesmo computador.
        """
        pygame.init()

        self.client = client
        self.is_network = client is not None
        self.my_player_id = client.player_id if client else None
        self._title_dirty = False
        self.connection_lost: bool = False

        # 1. Configuração da Janela
        info = pygame.display.Info()
        initial_w = int(info.current_w * 0.90)
        initial_h = int(info.current_h * 0.88)
        self.screen = pygame.display.set_mode((initial_w, initial_h), pygame.RESIZABLE)

        if self.is_network and self.client:
            pygame.display.set_caption(
                f"Quoridor Multiplayer - {self.client.player_name} (P{self.client.player_id})"
            )
        else:
            pygame.display.set_caption("Quoridor")
        self.clock = pygame.time.Clock()

        # Dimensões e escala
        current_w, current_h = self.screen.get_size()
        self.update_dimensions(current_w, current_h)

        # Estado da GUI
        self.input_mode: str = "PAWN"  # 'PAWN' ou 'WALL'
        self.wall_orientation: str = "H"  # 'H' ou 'V'
        self.status_message: str = (
            "Pressione SPACE para habilitar posicionamento de parede"
        )
        self.status_color = (200, 205, 220)
        self.error_message_time = 0

        if self.is_network and self.client:
            # Modo Rede: sincronização via callbacks assíncronos do Pyro5
            self.num_players = 2
            self.game = QuoridorGame(num_players=2)
            self.game.game_started = False

            self.client.add_listener(self._on_network_event)
            initial_state = self.client.get_game_state()
            self._apply_state(initial_state)
        else:
            # Modo Local: partida iniciada localmente
            self.num_players = num_players
            self.game = QuoridorGame(num_players=num_players)
            for i in range(1, num_players + 1):
                self.game.add_player(f"Jogador {i}")
            self.game.game_started = True

    # --- Sincronização de Rede (Pyro5) ---

    def _on_network_event(self, event_type: str, data: dict) -> None:
        """Callback executado na thread do Pyro5 ao receber atualizações remotas.

        Args:
            event_type: Identificador do evento (ex: 'state_changed', 'player_joined').
            data: Dicionário de payload com estado e/ou mensagem.
        """
        if event_type in ("state_changed", "game_started", "game_over"):
            state = data.get("state", data) if isinstance(data, dict) else data
            msg = data.get("message", "") if isinstance(data, dict) else ""
            self._apply_state(state, msg)
        elif event_type in ("player_joined", "player_left"):
            if self.client:
                state = self.client.get_game_state()
                self._apply_state(state)
        elif event_type == "player_id_changed":
            new_id = data.get("player_id") if isinstance(data, dict) else data
            self.my_player_id = new_id
            self._title_dirty = True
        elif event_type == "connection_lost":
            self.connection_lost = True
            self.status_message = "Conexão com o servidor perdida!"
            self.status_color = (230, 57, 70)

    def _apply_state(self, state: dict, message: str = "") -> None:
        """Aplica o dicionário de estado remoto na instância local do jogo.

        Args:
            state: Dicionário contendo os dados sincronizados do servidor.
            message: Mensagem explicativa opcional a ser exibida na barra de status.
        """
        if not state:
            return

        if message:
            self.status_message = message
            self.status_color = (200, 205, 220)

        is_started = state.get("game_started", False)
        self.game.game_started = is_started

        if not is_started:
            self.game.winner = None
            if (
                self.client
                and self.client.player_id
                and self.my_player_id != self.client.player_id
            ):
                self.my_player_id = self.client.player_id
                self._title_dirty = True
            return

        num_players = state.get("num_players", self.num_players)
        if num_players in (2, 4) and num_players != self.game.num_players:
            self.game = QuoridorGame(num_players=num_players)
            self.num_players = num_players

        sync_game_from_state(self.game, state)

    def reset_game(self) -> None:
        """Reinicia o jogo (no servidor em modo rede, ou localmente)."""
        if self.is_network and self.client:
            self.client.reset_game()
        else:
            self.game = QuoridorGame(num_players=self.num_players)
            for i in range(1, self.num_players + 1):
                self.game.add_player(f"Jogador {i}")
            self.game.game_started = True
            self.status_message = (
                "Pressione SPACE para habilitar posicionamento de parede"
            )
            self.input_mode = "PAWN"
            self.wall_orientation = "H"
            self.error_message_time = 0

    # --- Cálculos Geométricos e Responsividade ---

    def update_dimensions(self, width: int, height: int) -> None:
        """Recalcula dimensões do tabuleiro, ranhuras e fontes para manter a interface responsiva.

        Args:
            width: Nova largura da janela em pixels.
            height: Nova altura da janela em pixels.
        """
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

        # Fontes responsivas proporcionais ao tamanho das células
        self.font_title = pygame.font.SysFont(
            "arial", max(16, int(self.cell_size * 0.46)), bold=True
        )
        self.font_card_name = pygame.font.SysFont(
            "arial", max(14, int(self.cell_size * 0.36)), bold=True
        )
        self.font_hud = pygame.font.SysFont(
            "arial", max(12, int(self.cell_size * 0.28)), bold=True
        )
        self.font_pawn = pygame.font.SysFont(
            "arial", max(13, int(self.cell_size * 0.36)), bold=True
        )
        self.font_small = pygame.font.SysFont(
            "arial", max(10, int(self.cell_size * 0.24))
        )

    def get_cell_rect(self, row: int, col: int) -> pygame.Rect:
        """Retorna o retângulo de uma célula (row, col) em coordenadas de tela.

        Args:
            row: Índice da linha (0 a 8).
            col: Índice da coluna (0 a 8).

        Returns:
            `pygame.Rect` com coordenadas e dimensões da casa.
        """
        x = self.offset_x + col * (self.cell_size + self.groove_size)
        y = self.offset_y + row * (self.cell_size + self.groove_size)
        return pygame.Rect(x, y, self.cell_size, self.cell_size)

    def get_wall_rect(self, row: int, col: int, orientation: str) -> pygame.Rect:
        """Retorna o retângulo de uma parede de 2 posições em pixels.

        Args:
            row: Linha de ancoragem (0 a 7).
            col: Coluna de ancoragem (0 a 7).
            orientation: 'H' para horizontal, 'V' para vertical.

        Returns:
            `pygame.Rect` cobrindo a ranhura de 2 casas de comprimento.
        """
        x = self.offset_x + col * (self.cell_size + self.groove_size)
        y = self.offset_y + row * (self.cell_size + self.groove_size)

        if orientation == "H":
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
        """Identifica qual das 81 células está sob o cursor do mouse.

        Args:
            mouse_pos: Coordenadas (x, y) do ponteiro do mouse na janela.

        Returns:
            Tupla (linha, coluna) ou None se o cursor estiver fora do grid.
        """
        mx, my = mouse_pos
        for r in range(9):
            for c in range(9):
                if self.get_cell_rect(r, c).collidepoint(mx, my):
                    return (r, c)
        return None

    def get_hovered_wall_slot(
        self, mouse_pos: tuple[int, int]
    ) -> tuple[int, int] | None:
        """Localiza a interseção de parede (0-7, 0-7) mais próxima do cursor do mouse.

        Args:
            mouse_pos: Coordenadas (x, y) do mouse.

        Returns:
            Tupla (linha, coluna) da interseção mais próxima dentro do raio limite, ou None.
        """
        mx, my = mouse_pos
        threshold = self.cell_size // 2 + self.groove_size

        for r in range(8):
            for c in range(8):
                center_x = (
                    self.offset_x
                    + c * (self.cell_size + self.groove_size)
                    + self.cell_size
                    + self.groove_size // 2
                )
                center_y = (
                    self.offset_y
                    + r * (self.cell_size + self.groove_size)
                    + self.cell_size
                    + self.groove_size // 2
                )

                distance = ((mx - center_x) ** 2 + (my - center_y) ** 2) ** 0.5
                if distance <= threshold:
                    return (r, c)
        return None

    # --- Renderização Gráfica ---

    def draw_player_card(self, player, rect: pygame.Rect) -> None:
        """Renderiza o card lateral contendo avatar, nome, indicador de turno e paredes restantes.

        Args:
            player: Instância do jogador a ser exibido.
            rect: `pygame.Rect` delimitando a área do card.
        """
        is_turn = self.game.turn == player.id and not self.game.winner
        color = PLAYER_COLORS.get(player.id, (255, 255, 255))
        border_color = color if is_turn else CARD_BORDER_INACTIVE
        border_width = 3 if is_turn else 1

        # Moldura do card
        pygame.draw.rect(self.screen, CARD_BG_COLOR, rect, border_radius=12)
        pygame.draw.rect(
            self.screen, border_color, rect, width=border_width, border_radius=12
        )

        # Avatar
        avatar_radius = max(14, int(self.cell_size * 0.32))
        avatar_center = (rect.x + avatar_radius + 18, rect.y + avatar_radius + 18)
        draw_smooth_circle(
            self.screen,
            avatar_center,
            avatar_radius,
            color,
            border_color=(15, 17, 22),
            border_width=2,
        )
        avatar_label = self.font_hud.render(f"P{player.id}", True, (15, 17, 22))
        self.screen.blit(avatar_label, avatar_label.get_rect(center=avatar_center))

        # Nome
        is_me = self.is_network and self.client and player.id == self.client.player_id
        display_name = "Você" if is_me else player.name
        name_surf = self.font_card_name.render(display_name, True, (240, 242, 250))
        self.screen.blit(
            name_surf, (avatar_center[0] + avatar_radius + 16, rect.y + 20)
        )

        # Indicador de turno
        if not getattr(player, "is_active", True):
            status_str = "ELIMINADO"
            status_color = (220, 60, 60)
        else:
            status_str = "SUA VEZ" if is_turn else "AGUARDANDO"
            status_color = color if is_turn else (120, 125, 145)
        status_surf = self.font_small.render(status_str, True, status_color)
        self.screen.blit(
            status_surf, (avatar_center[0] + avatar_radius + 16, rect.y + 52)
        )

        # Divisor
        divider_y = rect.y + int(rect.height * 0.50)
        pygame.draw.line(
            self.screen,
            (45, 48, 62),
            (rect.x + 18, divider_y),
            (rect.right - 18, divider_y),
            1,
        )

        # Texto de paredes
        walls_text = f"Paredes: {player.remaining_walls} / {self.game.walls_per_player}"
        walls_surf = self.font_hud.render(walls_text, True, (210, 215, 230))
        self.screen.blit(
            walls_surf,
            (rect.x + (rect.width - walls_surf.get_width()) // 2, divider_y + 12),
        )

        # Barras de contagem de paredes
        block_w = max(10, int(self.cell_size * 0.22))
        block_h = max(12, int(self.cell_size * 0.26))
        gap = max(3, int(self.cell_size * 0.06))
        total_blocks_w = (
            self.game.walls_per_player * block_w
            + (self.game.walls_per_player - 1) * gap
        )
        start_x = rect.x + (rect.width - total_blocks_w) // 2
        bar_y = divider_y + 40

        for i in range(self.game.walls_per_player):
            block_color = color if i < player.remaining_walls else (45, 48, 62)
            pygame.draw.rect(
                self.screen,
                block_color,
                (start_x, bar_y, block_w, block_h),
                border_radius=2,
            )
            start_x += block_w + gap

    def draw_sidebars(self) -> None:
        """Renderiza as barras laterais dos jogadores para 2 ou 4 participantes."""
        side_width = min(320, max(180, self.offset_x - 50))
        left_x = (self.offset_x - side_width) // 2
        right_x = self.offset_x + self.board_size + (self.offset_x - side_width) // 2
        card_height = max(150, int(self.board_size * 0.28))

        if self.game.num_players == 2:
            center_y = self.offset_y + (self.board_size - card_height) // 2
            self.draw_player_card(
                self.game.players[1],
                pygame.Rect(left_x, center_y, side_width, card_height),
            )
            self.draw_player_card(
                self.game.players[2],
                pygame.Rect(right_x, center_y, side_width, card_height),
            )

        elif self.game.num_players == 4:
            gap = 18
            total_h = 2 * card_height + gap
            start_y = self.offset_y + (self.board_size - total_h) // 2

            self.draw_player_card(
                self.game.players[1],
                pygame.Rect(left_x, start_y, side_width, card_height),
            )
            self.draw_player_card(
                self.game.players[3],
                pygame.Rect(
                    left_x, start_y + card_height + gap, side_width, card_height
                ),
            )

            self.draw_player_card(
                self.game.players[2],
                pygame.Rect(right_x, start_y, side_width, card_height),
            )
            self.draw_player_card(
                self.game.players[4],
                pygame.Rect(
                    right_x, start_y + card_height + gap, side_width, card_height
                ),
            )

    def draw_target_goal_edge(self) -> None:
        """Destaca com a cor do jogador o objetivo de linha que ele deve alcançar."""
        if self.game.winner:
            return

        current = self.game.players.get(self.game.turn)
        if current is None or not getattr(current, "is_active", True):
            return

        color = PLAYER_COLORS.get(current.id, (255, 255, 255))
        edge_thickness = max(4, int(self.groove_size * 0.55))

        if current.target_axis == 0:
            if current.target_value == 8:
                # Linha de baixo (P1)
                y = self.offset_y + self.board_size + 4
                pygame.draw.rect(
                    self.screen,
                    color,
                    (self.offset_x, y, self.board_size, edge_thickness),
                    border_radius=3,
                )
            elif current.target_value == 0:
                # Linha de cima (P2)
                y = self.offset_y - edge_thickness - 4
                pygame.draw.rect(
                    self.screen,
                    color,
                    (self.offset_x, y, self.board_size, edge_thickness),
                    border_radius=3,
                )
        elif current.target_axis == 1:
            if current.target_value == 8:
                # Linha da direita (P3)
                x = self.offset_x + self.board_size + 4
                pygame.draw.rect(
                    self.screen,
                    color,
                    (x, self.offset_y, edge_thickness, self.board_size),
                    border_radius=3,
                )
            elif current.target_value == 0:
                # Linha da esquerda (P4)
                x = self.offset_x - edge_thickness - 4
                pygame.draw.rect(
                    self.screen,
                    color,
                    (x, self.offset_y, edge_thickness, self.board_size),
                    border_radius=3,
                )

    def draw_board(self, mouse_pos: tuple[int, int]) -> None:
        """Renderiza o tabuleiro, células, projeções de movimentos válidos, paredes e peões.

        Args:
            mouse_pos: Coordenadas atuais (x, y) do mouse para cálculo de hover e previews.
        """
        board_rect = pygame.Rect(
            self.offset_x - 12,
            self.offset_y - 12,
            self.board_size + 24,
            self.board_size + 24,
        )
        pygame.draw.rect(self.screen, BOARD_BG_COLOR, board_rect, border_radius=10)

        # Destaca borda alvo
        self.draw_target_goal_edge()

        current_player = self.game.players.get(self.game.turn)
        if current_player is None or not getattr(current_player, "is_active", True):
            current_color = (255, 255, 255)
            valid_moves = []
        else:
            current_color = PLAYER_COLORS.get(current_player.id, (255, 255, 255))
            valid_moves = (
                self.game.get_valid_moves(current_player.id)
                if not self.game.winner
                else []
            )
        hovered_cell = self.get_hovered_cell(mouse_pos)

        # 1. Células
        for r in range(9):
            for c in range(9):
                rect = self.get_cell_rect(r, c)
                color = CELL_HOVER_COLOR if (r, c) == hovered_cell else CELL_COLOR
                pygame.draw.rect(self.screen, color, rect, border_radius=6)

                # Projeção de movimentos válidos
                if (r, c) in valid_moves:
                    draw_smooth_circle(
                        self.screen,
                        rect.center,
                        int(self.cell_size * 0.22),
                        (*current_color, 150),
                    )
                    draw_smooth_circle(
                        self.screen,
                        rect.center,
                        int(self.cell_size * 0.10),
                        current_color,
                    )

        # 2. Paredes já posicionadas
        for wall in self.game.walls:
            r, c = wall.position
            wall_rect = self.get_wall_rect(r, c, wall.orientation)
            pygame.draw.rect(self.screen, WALL_COLOR, wall_rect, border_radius=4)

        # 3. Preview de Parede (Ghost)
        hovered_wall_slot = self.get_hovered_wall_slot(mouse_pos)
        can_show_ghost = (
            self.input_mode == "WALL"
            and hovered_wall_slot is not None
            and not self.game.winner
            and current_player is not None
            and getattr(current_player, "is_active", True)
            and current_player.remaining_walls > 0
            and (not self.is_network or self.game.turn == self.client.player_id)
        )
        if can_show_ghost and current_player is not None:
            hr, hc = hovered_wall_slot
            preview_wall = Wall((hr, hc), self.wall_orientation)
            can_place, _ = self.game.can_place_wall(current_player.id, preview_wall)

            ghost_color = GHOST_VALID_COLOR if can_place else GHOST_INVALID_COLOR
            ghost_rect = self.get_wall_rect(hr, hc, self.wall_orientation)

            ghost_surface = pygame.Surface(
                (ghost_rect.width, ghost_rect.height), pygame.SRCALPHA
            )
            ghost_surface.fill(ghost_color)
            self.screen.blit(ghost_surface, ghost_rect.topleft)

        # 4. Peões
        for player in self.game.players.values():
            if not getattr(player, "is_active", True):
                continue
            r, c = player.position
            center = self.get_cell_rect(r, c).center
            color = PLAYER_COLORS.get(player.id, (255, 255, 255))
            radius = self.cell_size // 2 - 8

            draw_smooth_circle(
                self.screen,
                center,
                radius,
                color,
                border_color=(15, 17, 22),
                border_width=3,
            )

    def draw_hud(self) -> None:
        """Renderiza o cabeçalho superior informando turno e feedback de status inferior."""
        if not self.game.game_started:
            return

        if self.game.winner:
            winner = self.game.players[self.game.winner]
            color = PLAYER_COLORS.get(winner.id, (255, 255, 255))
            win_text = f"{winner.name} venceu a partida!"
            win_surf = self.font_title.render(win_text, True, color)
            self.screen.blit(
                win_surf,
                (
                    self.screen_width // 2 - win_surf.get_width() // 2,
                    self.offset_y - 50,
                ),
            )

            hint_text = "Pressione ENTER para jogar novamente"
            hint_surf = self.font_hud.render(hint_text, True, (200, 205, 220))
            self.screen.blit(
                hint_surf,
                (
                    self.screen_width // 2 - hint_surf.get_width() // 2,
                    self.offset_y + self.board_size + 24,
                ),
            )
            return

        # Cabeçalho de Turno
        current = self.game.players.get(self.game.turn)
        if current is None or not getattr(current, "is_active", True):
            return
        current_color = PLAYER_COLORS.get(current.id, (255, 255, 255))

        if self.is_network and self.client:
            is_my_turn = self.game.turn == self.client.player_id
            turn_text = (
                f"Sua vez, {current.name}"
                if is_my_turn
                else f"Vez de {current.name}, aguardando..."
            )
        else:
            turn_text = f"Vez de {current.name}"

        turn_surf = self.font_title.render(turn_text, True, current_color)
        self.screen.blit(
            turn_surf,
            (self.screen_width // 2 - turn_surf.get_width() // 2, self.offset_y - 50),
        )

        # Mensagem de Status Inferior
        if self.status_message:
            msg_surf = self.font_hud.render(
                self.status_message, True, self.status_color
            )
            self.screen.blit(
                msg_surf,
                (
                    self.screen_width // 2 - msg_surf.get_width() // 2,
                    self.offset_y + self.board_size + 24,
                ),
            )

    def draw_lobby(self) -> None:
        """Renderiza a sala de espera (lobby) no modo multiplayer."""
        if not self.client:
            return

        state = self.client.get_game_state()
        lobby_players = state.get("lobby", [])
        can_start = state.get("can_start", False)
        count = len(lobby_players)

        # Título do Lobby
        title_surf = self.font_title.render(
            "SALA MULTIPLAYER - QUORIDOR", True, (255, 183, 3)
        )
        self.screen.blit(
            title_surf,
            (
                self.screen_width // 2 - title_surf.get_width() // 2,
                self.screen_height // 4,
            ),
        )

        # Subtítulo com contagem
        count_str = f"Jogadores conectados: {count} / 4  - Mínimo 2, Máximo 4"
        count_surf = self.font_card_name.render(count_str, True, (210, 215, 230))
        self.screen.blit(
            count_surf,
            (
                self.screen_width // 2 - count_surf.get_width() // 2,
                self.screen_height // 4 + 50,
            ),
        )

        # Lista de jogadores no Lobby
        card_w = min(400, int(self.screen_width * 0.45))
        card_h = 55
        start_y = self.screen_height // 4 + 110

        for idx, p in enumerate(lobby_players):
            pid = p["id"]
            pname = p["name"]
            is_me = pid == self.client.player_id
            color = PLAYER_COLORS.get(pid, (255, 255, 255))

            rect = pygame.Rect(
                (self.screen_width - card_w) // 2,
                start_y + idx * (card_h + 12),
                card_w,
                card_h,
            )
            pygame.draw.rect(self.screen, CARD_BG_COLOR, rect, border_radius=8)
            border_c = color if is_me else CARD_BORDER_INACTIVE
            pygame.draw.rect(self.screen, border_c, rect, width=2, border_radius=8)

            # Avatar
            avatar_center = (rect.x + 30, rect.centery)
            draw_smooth_circle(
                self.screen,
                avatar_center,
                18,
                color,
                border_color=(15, 17, 22),
                border_width=2,
            )
            lbl = self.font_small.render(f"P{pid}", True, (15, 17, 22))
            self.screen.blit(lbl, lbl.get_rect(center=avatar_center))

            # Nome
            display_name = "Você" if is_me else pname
            name_surf = self.font_card_name.render(display_name, True, (240, 242, 250))
            self.screen.blit(
                name_surf,
                (avatar_center[0] + 30, rect.centery - name_surf.get_height() // 2),
            )

        # Instruções de Início
        instruction_y = start_y + 4 * (card_h + 12) + 20
        if can_start:
            msg = "Pressione ENTER ou ESPAÇO para INICIAR a partida!"
            msg_color = (6, 214, 160)
        else:
            msg = (
                "Aguardando mais jogadores para iniciar, é necessário 2 ou 4 jogadores."
            )
            msg_color = (255, 209, 102)

        inst_surf = self.font_card_name.render(msg, True, msg_color)
        self.screen.blit(
            inst_surf,
            (self.screen_width // 2 - inst_surf.get_width() // 2, instruction_y),
        )

    def draw_connection_lost_overlay(self) -> None:
        """Renderiza um aviso visual modal sobreposto quando a conexão com o servidor é perdida."""
        # Escurece o fundo
        dim_surf = pygame.Surface(
            (self.screen_width, self.screen_height), pygame.SRCALPHA
        )
        dim_surf.fill((10, 12, 18, 215))
        self.screen.blit(dim_surf, (0, 0))

        # Painel central de alerta
        panel_w = min(540, int(self.screen_width * 0.85))
        panel_h = 200
        panel_rect = pygame.Rect(
            (self.screen_width - panel_w) // 2,
            (self.screen_height - panel_h) // 2,
            panel_w,
            panel_h,
        )

        pygame.draw.rect(self.screen, CARD_BG_COLOR, panel_rect, border_radius=14)
        pygame.draw.rect(
            self.screen, (230, 57, 70), panel_rect, width=2, border_radius=14
        )

        # Título em destaque vermelho
        title_surf = self.font_title.render(
            "CONEXÃO COM O SERVIDOR PERDIDA", True, (230, 57, 70)
        )
        self.screen.blit(
            title_surf,
            (
                panel_rect.centerx - title_surf.get_width() // 2,
                panel_rect.y + 35,
            ),
        )

        # Descrição explicativa
        desc_surf = self.font_card_name.render(
            "O servidor caiu ou a comunicação foi interrompida.",
            True,
            (210, 215, 230),
        )
        self.screen.blit(
            desc_surf,
            (
                panel_rect.centerx - desc_surf.get_width() // 2,
                panel_rect.y + 85,
            ),
        )

        # Instrução para sair
        hint_surf = self.font_hud.render(
            "Pressione ESC para fechar a aplicação.", True, (255, 183, 3)
        )
        self.screen.blit(
            hint_surf,
            (
                panel_rect.centerx - hint_surf.get_width() // 2,
                panel_rect.y + 135,
            ),
        )

    # --- Tratamento de Input ---

    def handle_mouse_click(self, mouse_pos: tuple[int, int]) -> None:
        """Processa clique do mouse para movimentar peão ou colocar parede conforme o modo ativo.

        Args:
            mouse_pos: Coordenadas (x, y) do clique do mouse na tela.
        """
        if self.connection_lost or not self.game.game_started or self.game.winner:
            return

        if self.is_network and self.client and self.game.turn != self.client.player_id:
            self.status_message = (
                f"Não é a sua vez! Aguarde a jogada do Jogador {self.game.turn}."
            )
            self.status_color = (230, 57, 70)
            self.error_message_time = pygame.time.get_ticks()
            return

        current_player = self.game.players[self.game.turn]

        if self.input_mode == "PAWN":
            clicked_cell = self.get_hovered_cell(mouse_pos)
            if clicked_cell:
                if self.is_network and self.client:
                    valid_moves = self.client.get_valid_moves()
                    if clicked_cell in valid_moves:
                        success, msg = self.client.move_player(clicked_cell)
                        if not success:
                            self.status_message = msg
                            self.status_color = (230, 57, 70)
                            self.error_message_time = pygame.time.get_ticks()
                else:
                    valid_moves = self.game.get_valid_moves(current_player.id)
                    if clicked_cell in valid_moves:
                        success, msg = self.game.move_player(
                            current_player.id, clicked_cell
                        )
                        if success:
                            self.status_message = (
                                "Pressione SPACE para desabilitar posicionamento de parede"
                                if self.input_mode == "WALL"
                                else "Pressione SPACE para habilitar posicionamento de parede"
                            )
                            self.status_color = (200, 205, 220)
                            self.error_message_time = 0
                        else:
                            self.status_message = msg
                            self.status_color = (230, 57, 70)
                            self.error_message_time = pygame.time.get_ticks()

        elif self.input_mode == "WALL":
            clicked_wall_slot = self.get_hovered_wall_slot(mouse_pos)
            if clicked_wall_slot:
                if current_player.remaining_walls <= 0:
                    self.status_message = "Você não tem mais paredes disponíveis!"
                    self.status_color = (230, 57, 70)
                    self.error_message_time = pygame.time.get_ticks()
                    return

                if self.is_network and self.client:
                    success, msg = self.client.place_wall(
                        clicked_wall_slot, self.wall_orientation
                    )
                    if not success:
                        self.status_message = msg
                        self.status_color = (230, 57, 70)
                        self.error_message_time = pygame.time.get_ticks()
                else:
                    new_wall = Wall(clicked_wall_slot, self.wall_orientation)
                    success, msg = self.game.place_wall(current_player.id, new_wall)
                    if success:
                        self.status_message = (
                            "Pressione SPACE para desabilitar posicionamento de parede"
                            if self.input_mode == "WALL"
                            else "Pressione SPACE para habilitar posicionamento de parede"
                        )
                        self.status_color = (200, 205, 220)
                        self.error_message_time = 0
                    else:
                        self.status_message = msg
                        self.status_color = (230, 57, 70)
                        self.error_message_time = pygame.time.get_ticks()

    def run(self) -> None:
        """Executa o loop principal de renderização, captura de inputs e eventos Pygame."""
        running = True
        while running:
            mouse_pos = pygame.mouse.get_pos()

            if (
                self.error_message_time > 0
                and pygame.time.get_ticks() - self.error_message_time > 3000
            ):
                self.status_message = (
                    "Pressione SPACE para desabilitar posicionamento de parede"
                    if self.input_mode == "WALL"
                    else "Pressione SPACE para habilitar posicionamento de parede"
                )
                self.status_color = (200, 205, 220)
                self.error_message_time = 0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.VIDEORESIZE:
                    new_w = max(640, event.w)
                    new_h = max(480, event.h)
                    self.screen = pygame.display.set_mode(
                        (new_w, new_h), pygame.RESIZABLE
                    )
                    self.update_dimensions(new_w, new_h)

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE or (
                        self.connection_lost
                        and event.key in (pygame.K_RETURN, pygame.K_SPACE)
                    ):
                        running = False

                    elif (
                        not self.connection_lost
                        and event.key in (pygame.K_RETURN, pygame.K_SPACE)
                        and self.is_network
                        and not self.game.game_started
                    ):
                        if self.client:
                            ok, msg = self.client.start_game()
                            if not ok:
                                self.status_message = msg
                                self.status_color = (230, 57, 70)
                                self.error_message_time = pygame.time.get_ticks()

                    elif event.key == pygame.K_r:
                        self.wall_orientation = (
                            "V" if self.wall_orientation == "H" else "H"
                        )

                    elif event.key == pygame.K_SPACE and self.game.game_started:
                        self.input_mode = (
                            "WALL" if self.input_mode == "PAWN" else "PAWN"
                        )
                        self.status_message = (
                            "Pressione SPACE para desabilitar posicionamento de parede"
                            if self.input_mode == "WALL"
                            else "Pressione SPACE para habilitar posicionamento de parede"
                        )
                        self.status_color = (200, 205, 220)
                        self.error_message_time = 0

                    elif (
                        event.key == pygame.K_RETURN
                        and self.game.winner
                        and not self.connection_lost
                    ):
                        self.reset_game()

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self.handle_mouse_click(mouse_pos)
                    elif event.button == 3:
                        self.wall_orientation = (
                            "V" if self.wall_orientation == "H" else "H"
                        )

            self.screen.fill(BG_COLOR)

            if self.is_network and not self.game.game_started:
                self.draw_lobby()
            else:
                self.draw_board(mouse_pos)
                self.draw_sidebars()
                self.draw_hud()

            if self.connection_lost:
                self.draw_connection_lost_overlay()

            if self._title_dirty:
                self._title_dirty = False
                if self.client and self.client.player_id:
                    pygame.display.set_caption(
                        f"Quoridor Multiplayer - {self.client.player_name} (P{self.client.player_id})"
                    )

            pygame.display.flip()
            self.clock.tick(FPS)

        if self.is_network and self.client:
            self.client.disconnect()

        pygame.quit()
        sys.exit()
