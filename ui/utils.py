import pygame


def draw_smooth_circle(
    surface: pygame.Surface,
    center: tuple[int, int],
    radius: int,
    color: tuple[int, int, int] | tuple[int, int, int, int],
    border_color: tuple[int, int, int] | None = None,
    border_width: int = 0,
) -> None:
    """Renderiza um círculo suave com anti-aliasing de alta qualidade via supersampling 4x.

    Desenha o círculo e sua borda opcional em uma superfície ampliada temporária e
    aplica smoothscale para eliminar serrilhados.

    Args:
        surface: Superfície Pygame de destino.
        center: Coordenadas centrais (x, y) em pixels.
        radius: Raio do círculo em pixels.
        color: Cor de preenchimento (RGB ou RGBA).
        border_color: Cor da borda opcional (RGB).
        border_width: Espessura da borda em pixels (0 para sem borda).
    """
    scale = 4
    d = (radius + border_width + 2) * 2
    surf = pygame.Surface((d * scale, d * scale), pygame.SRCALPHA)
    c = (d * scale) // 2
    r_scaled = radius * scale

    pygame.draw.circle(surf, color, (c, c), r_scaled)
    if border_color and border_width > 0:
        pygame.draw.circle(surf, border_color, (c, c), r_scaled, border_width * scale)

    smooth = pygame.transform.smoothscale(surf, (d, d))
    surface.blit(smooth, (center[0] - d // 2, center[1] - d // 2))
