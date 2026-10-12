from __future__ import annotations
import sys
import pygame
from core.game import QuoridorGame
from core.models import Wall
from network.client import QuoridorClient
from network.protocol import sync_game_from_state
from ui.constants import *
from ui.gui import QuoridorGUI
from ui.utils import draw_smooth_circle


class QuoridorNetworkGUI(QuoridorGUI):
    """Interface gráfica do Quoridor adaptada para o modo multiplayer em rede.

    Não realiza polling: o estado do jogo é atualizado de forma reativa e instantânea
    através dos callbacks recebidos pelo QuoridorClient via Pyro5.
    """

    def __init__(self, client: QuoridorClient) -> None:
        self.client = client
        self.my_player_id = client.player_id

        # Inicializa o Pygame e configurações gráficas base
        super().__init__(num_players=2)
        pygame.display.set_caption(f"Quoridor Multiplayer - {client.player_name} (P{client.player_id})")

        # Escuta os eventos recebidos do servidor via callback oneway
        self.client.add_listener(self._on_network_event)

        # Sincroniza estado inicial recebido
        initial_state = self.client.get_game_state()
        self._apply_state(initial_state)

    def _on_network_event(self, event_type: str, data: dict) -> None:
        """Callback executado na thread de background do Pyro5 quando o servidor notifica mudanças."""
        if event_type in ("state_changed", "game_started", "game_over"):
            state = data.get("state", data) if isinstance(data, dict) else data
            msg = data.get("message", "") if isinstance(data, dict) else ""
            self._apply_state(state, msg)
        elif event_type in ("player_joined", "player_left"):
            state = self.client.get_game_state()
            self._apply_state(state)

    def _apply_state(self, state: dict, message: str = "") -> None:
        """Aplica o dicionário de estado remoto na instância local do jogo."""
        if not state:
            return

        if message:
            self.status_message = message
            self.status_color = (200, 205, 220)

        is_started = state.get("game_started", False)
        self.game.game_started = is_started

        if not is_started:
            self.game.winner = None
            return

        # Partida em andamento: atualiza número de jogadores se necessário (somente 2 ou 4)
        num_players = state.get("num_players", self.num_players)
        if num_players in (2, 4) and num_players != self.game.num_players:
            self.game = QuoridorGame(num_players=num_players)
            self.num_players = num_players

        sync_game_from_state(self.game, state)

    def draw_lobby(self) -> None:
        """Renderiza a tela de sala de espera (lobby)."""
        state = self.client.get_game_state()
        lobby_players = state.get("lobby", [])
        can_start = state.get("can_start", False)
        count = len(lobby_players)

        # Título do Lobby
        title_surf = self.font_title.render("SALA MULTIPLAYER - QUORIDOR", True, (255, 183, 3))
        self.screen.blit(title_surf, (self.screen_width // 2 - title_surf.get_width() // 2, self.screen_height // 4))

        # Subtítulo com contagem
        count_str = f"Jogadores conectados: {count} / 4  (Mínimo 2, Máximo 4)"
        count_surf = self.font_card_name.render(count_str, True, (210, 215, 230))
        self.screen.blit(count_surf, (self.screen_width // 2 - count_surf.get_width() // 2, self.screen_height // 4 + 50))

        # Lista de jogadores no Lobby
        card_w = min(400, int(self.screen_width * 0.45))
        card_h = 55
        start_y = self.screen_height // 4 + 110

        for idx, p in enumerate(lobby_players):
            pid = p["id"]
            pname = p["name"]
            is_me = (pid == self.client.player_id)
            color = PLAYER_COLORS.get(pid, (255, 255, 255))

            rect = pygame.Rect((self.screen_width - card_w) // 2, start_y + idx * (card_h + 12), card_w, card_h)
            pygame.draw.rect(self.screen, CARD_BG_COLOR, rect, border_radius=8)
            border_c = color if is_me else CARD_BORDER_INACTIVE
            pygame.draw.rect(self.screen, border_c, rect, width=2, border_radius=8)

            # Avatar
            avatar_center = (rect.x + 30, rect.centery)
            draw_smooth_circle(self.screen, avatar_center, 18, color, border_color=(15, 17, 22), border_width=2)
            lbl = self.font_small.render(f"P{pid}", True, (15, 17, 22))
            self.screen.blit(lbl, lbl.get_rect(center=avatar_center))

            # Nome
            display_name = f"{pname} (Você)" if is_me else pname
            name_surf = self.font_card_name.render(display_name, True, (240, 242, 250))
            self.screen.blit(name_surf, (avatar_center[0] + 30, rect.centery - name_surf.get_height() // 2))

        # Instruções de Início
        instruction_y = start_y + 4 * (card_h + 12) + 20
        if can_start:
            msg = "Pressione ENTER ou ESPAÇO para INICIAR a partida!"
            msg_color = (6, 214, 160)
        else:
            msg = "Aguardando mais jogadores para iniciar (necessário 2 ou 4)..."
            msg_color = (255, 209, 102)

        inst_surf = self.font_card_name.render(msg, True, msg_color)
        self.screen.blit(inst_surf, (self.screen_width // 2 - inst_surf.get_width() // 2, instruction_y))

    def handle_mouse_click(self, mouse_pos: tuple[int, int]) -> None:
        """Processa clique do mouse, validando o turno do jogador local."""
        if not self.game.game_started or self.game.winner:
            return

        if self.game.turn != self.client.player_id:
            self.status_message = f"Não é a sua vez! Aguarde a jogada do Jogador {self.game.turn}."
            self.status_color = (230, 57, 70)
            self.error_message_time = pygame.time.get_ticks()
            return

        current_player = self.game.players[self.client.player_id]

        if self.input_mode == 'PAWN':
            clicked_cell = self.get_hovered_cell(mouse_pos)
            if clicked_cell:
                valid_moves = self.client.get_valid_moves()
                if clicked_cell in valid_moves:
                    success, msg = self.client.move_player(clicked_cell)
                    if not success:
                        self.status_message = msg
                        self.status_color = (230, 57, 70)
                        self.error_message_time = pygame.time.get_ticks()
        elif self.input_mode == 'WALL':
            clicked_wall_slot = self.get_hovered_wall_slot(mouse_pos)
            if clicked_wall_slot:
                if current_player.remaining_walls <= 0:
                    self.status_message = "Você não tem mais paredes disponíveis!"
                    self.status_color = (230, 57, 70)
                    self.error_message_time = pygame.time.get_ticks()
                    return

                success, msg = self.client.place_wall(clicked_wall_slot, self.wall_orientation)
                if not success:
                    self.status_message = msg
                    self.status_color = (230, 57, 70)
                    self.error_message_time = pygame.time.get_ticks()

    def draw_hud(self) -> None:
        """Renderiza o cabeçalho superior informando turno e identificação do jogador local."""
        if not self.game.game_started:
            return

        if self.game.winner:
            super().draw_hud()
            return

        # Turno atual e indicador de jogador local
        is_my_turn = (self.game.turn == self.client.player_id)
        current = self.game.players[self.game.turn]
        current_color = PLAYER_COLORS.get(current.id, (255, 255, 255))

        if is_my_turn:
            turn_text = f"SUA VEZ! ({current.name})"
        else:
            turn_text = f"Vez de {current.name} (Aguardando...)"

        turn_surf = self.font_title.render(turn_text, True, current_color)
        self.screen.blit(turn_surf, (self.screen_width // 2 - turn_surf.get_width() // 2, self.offset_y - 50))

        # Dica / Feedback de status inferior
        if self.status_message:
            msg_surf = self.font_hud.render(self.status_message, True, self.status_color)
            self.screen.blit(msg_surf, (self.screen_width // 2 - msg_surf.get_width() // 2, self.offset_y + self.board_size + 24))

    def run(self) -> None:
        """Loop principal de eventos Pygame."""
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

                elif event.type == pygame.VIDEORESIZE:
                    new_w = max(640, event.w)
                    new_h = max(480, event.h)
                    self.screen = pygame.display.set_mode((new_w, new_h), pygame.RESIZABLE)
                    self.update_dimensions(new_w, new_h)

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and not self.game.game_started:
                        # Tenta iniciar a partida no lobby
                        ok, msg = self.client.start_game()
                        if not ok:
                            self.status_message = msg
                            self.status_color = (230, 57, 70)
                            self.error_message_time = pygame.time.get_ticks()
                    elif event.key == pygame.K_r:
                        self.wall_orientation = 'V' if self.wall_orientation == 'H' else 'H'
                    elif event.key == pygame.K_SPACE and self.game.game_started:
                        self.input_mode = 'WALL' if self.input_mode == 'PAWN' else 'PAWN'
                        self.status_message = (
                            "Pressione SPACE para desabilitar posicionamento de parede"
                            if self.input_mode == 'WALL'
                            else "Pressione SPACE para habilitar posicionamento de parede"
                        )
                        self.status_color = (200, 205, 220)
                        self.error_message_time = 0
                    elif event.key == pygame.K_RETURN and self.game.winner:
                        self.client.reset_game()

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self.handle_mouse_click(mouse_pos)
                    elif event.button == 3:
                        self.wall_orientation = 'V' if self.wall_orientation == 'H' else 'H'

            self.screen.fill(BG_COLOR)

            if not self.game.game_started:
                self.draw_lobby()
            else:
                self.draw_board(mouse_pos)
                self.draw_sidebars()
                self.draw_hud()

            pygame.display.flip()
            self.clock.tick(FPS)

        # Desconecta o cliente e encerra o Pygame
        self.client.disconnect()
        pygame.quit()
        sys.exit()
