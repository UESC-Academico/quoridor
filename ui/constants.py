"""Constantes visuais e paleta de cores da interface gráfica Pygame."""

# Taxa de quadros por segundo da janela
FPS = 60

# --- PALETA DE CORES ---
BG_COLOR = (22, 24, 30)  # Fundo geral da aplicação
BOARD_BG_COLOR = (32, 35, 45)  # Fundo da base do tabuleiro
CELL_COLOR = (46, 50, 65)  # Cor padrão das 81 casas do tabuleiro
CELL_HOVER_COLOR = (62, 67, 88)  # Destaque ao passar o mouse sobre a casa
GROOVE_COLOR = (26, 28, 36)  # Ranhuras entre casas onde as paredes se encaixam

CARD_BG_COLOR = (30, 33, 44)  # Fundo dos cards de status dos jogadores
CARD_BORDER_INACTIVE = (48, 52, 68)  # Borda do card quando não é a vez do jogador

# Cores de paredes e preview translúcido (RGBA)
WALL_COLOR = (255, 183, 3)  # Amarelo para paredes já posicionadas
GHOST_VALID_COLOR = (
    255,
    183,
    3,
    140,
)  # Preview amarelo transparente para posicionamento válido
GHOST_INVALID_COLOR = (
    230,
    57,
    70,
    140,
)  # Preview vermelho transparente para posição ilegal

# Cores temáticas para os peões e bordas-alvo de cada jogador (P1 a P4)
PLAYER_COLORS = {
    1: (72, 202, 228),  # P1: Azul
    2: (230, 57, 70),  # P2: Vermelho
    3: (255, 209, 102),  # P3: Amarelo
    4: (6, 214, 160),  # P4: Verde
}
