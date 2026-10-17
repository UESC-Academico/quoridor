from __future__ import annotations

import contextlib
import os
import re
import sys
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.game import QuoridorGame
from core.models import Wall

if TYPE_CHECKING:
    from network.client import QuoridorClient

# --- Configuração e Cores ANSI do Console ---

try:
    import msvcrt

    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False

COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_DIM = "\033[2m"
COLOR_CYAN = "\033[96m"  # Jogador 1
COLOR_RED = "\033[91m"  # Jogador 2
COLOR_YELLOW = "\033[93m"  # Jogador 3 / Paredes
COLOR_GREEN = "\033[92m"  # Jogador 4 / Destaques positivos
COLOR_MAGENTA = "\033[95m"
COLOR_GRAY = "\033[90m"
BG_CURRENT = "\033[44m"

PLAYER_COLORS = {
    1: COLOR_CYAN,
    2: COLOR_RED,
    3: COLOR_YELLOW,
    4: COLOR_GREEN,
}


def init_console() -> None:
    """Configura o console para suporte a UTF-8 e sequências de escape ANSI."""
    if hasattr(sys.stdout, "reconfigure"):
        with contextlib.suppress(AttributeError, ValueError, OSError):
            sys.stdout.reconfigure(encoding="utf-8")
    if os.name == "nt":
        # Ativa o modo de processamento VT100 no Windows
        os.system("")


def clear_screen() -> None:
    """Limpa o console do cliente de forma compatível com Windows e Unix."""
    os.system("cls" if os.name == "nt" else "clear")


# --- Estruturas de Dados do Tabuleiro para Exibição ---


@dataclass
class BoardViewData:
    players: dict[int, dict[str, Any]]
    walls: set[tuple[tuple[int, int], str]]
    turn: int
    winner: int | None
    walls_per_player: int
    num_players: int


def extract_view_from_game(game: QuoridorGame) -> BoardViewData:
    """Extrai informações visuais a partir de uma instância local de QuoridorGame."""
    players: dict[int, dict[str, Any]] = {}
    for pid, p in game.players.items():
        players[pid] = {
            "id": p.id,
            "name": p.name,
            "position": tuple(p.position),
            "remaining_walls": p.remaining_walls,
            "target_axis": p.target_axis,
            "target_value": p.target_value,
        }
    walls = {(tuple(w.position), w.orientation) for w in game.walls}
    return BoardViewData(
        players=players,
        walls=walls,
        turn=game.turn,
        winner=game.winner,
        walls_per_player=game.walls_per_player,
        num_players=game.num_players,
    )


def extract_view_from_state(state: dict[str, Any]) -> BoardViewData:
    """Extrai informações visuais a partir do dicionário de estado remoto do servidor."""
    players: dict[int, dict[str, Any]] = {}
    raw_players = state.get("players", {})
    for pid_str, p in raw_players.items():
        pid = int(pid_str)
        players[pid] = {
            "id": pid,
            "name": p.get("name", f"Jogador {pid}"),
            "position": tuple(p.get("position", (0, 0))),
            "remaining_walls": p.get("remaining_walls", 0),
            "target_axis": p.get("target_axis", 0),
            "target_value": p.get("target_value", 8),
        }

    raw_walls = state.get("walls", [])
    walls = set()
    for w in raw_walls:
        pos = tuple(w.get("position", (0, 0)))
        ori = w.get("orientation", "H")
        walls.add((pos, ori))

    num_players = state.get("num_players", len(players) or 2)
    return BoardViewData(
        players=players,
        walls=walls,
        turn=state.get("turn", 1),
        winner=state.get("winner"),
        walls_per_player=state.get("walls_per_player", 10 if num_players == 2 else 5),
        num_players=num_players,
    )


# --- Renderizadores do Tabuleiro e HUD ---


def render_board(
    view: BoardViewData,
    valid_moves: list[tuple[int, int]] | None = None,
    use_color: bool = True,
) -> list[str]:
    """Renderiza o grid 9x9 do tabuleiro com peões e paredes em formato ASCII/Unicode."""
    r_rst = COLOR_RESET if use_color else ""
    r_bld = COLOR_BOLD if use_color else ""
    r_gry = COLOR_GRAY if use_color else ""
    r_yel = COLOR_YELLOW + r_bld if use_color else ""
    r_grn = COLOR_GREEN + r_bld if use_color else ""

    player_pos_map: dict[tuple[int, int], int] = {}
    for pid, p in view.players.items():
        player_pos_map[p["position"]] = pid

    valid_set = set(valid_moves or [])

    lines: list[str] = []
    lines.append("      0   1   2   3   4   5   6   7   8")
    lines.append(f"    {r_gry}┌───┬───┬───┬───┬───┬───┬───┬───┬───┐{r_rst}")

    for r in range(9):
        # 1. Linha das Células
        row_str = f"  {r} {r_gry}│{r_rst}"
        for c in range(9):
            pos = (r, c)
            if pos in player_pos_map:
                pid = player_pos_map[pos]
                color = (
                    (PLAYER_COLORS.get(pid, COLOR_RESET) + r_bld) if use_color else ""
                )
                cell_content = f"{color} P{pid}{r_rst}"
            elif pos in valid_set:
                cell_content = f"{r_grn} · {r_rst}"
            else:
                cell_content = f"{r_gry} · {r_rst}"

            row_str += cell_content

            if c < 8:
                # Parede vertical à direita de (r, c)
                has_v = ((r, c), "V") in view.walls or ((r - 1, c), "V") in view.walls
                sep = f"{r_yel}║{r_rst}" if has_v else f"{r_gry}│{r_rst}"
                row_str += sep

        row_str += f"{r_gry}│{r_rst} {r}"
        lines.append(row_str)

        # 2. Linha Divisória Horizontal entre Linhas
        if r < 8:
            sep_str = f"    {r_gry}├{r_rst}"
            for c in range(9):
                # Parede horizontal abaixo de (r, c)
                has_h = ((r, c), "H") in view.walls or ((r, c - 1), "H") in view.walls
                h_segment = f"{r_yel}═══{r_rst}" if has_h else f"{r_gry}───{r_rst}"
                sep_str += h_segment

                if c < 8:
                    if ((r, c), "H") in view.walls:
                        cross = f"{r_yel}═{r_rst}"
                    elif ((r, c), "V") in view.walls:
                        cross = f"{r_yel}║{r_rst}"
                    else:
                        cross = f"{r_gry}┼{r_rst}"
                    sep_str += cross

            sep_str += f"{r_gry}┤{r_rst}"
            lines.append(sep_str)

    lines.append(f"    {r_gry}└───┴───┴───┴───┴───┴───┴───┴───┴───┘{r_rst}")
    lines.append("      0   1   2   3   4   5   6   7   8")
    return lines


def render_game_info(
    view: BoardViewData,
    local_player_id: int | None = None,
    server_name: str = "",
    last_action: str = "",
    error_message: str = "",
    valid_moves: list[tuple[int, int]] | None = None,
    use_color: bool = True,
) -> list[str]:
    """Monta a tela completa de jogo: cabeçalho, tabuleiro, placar e instruções."""
    r_rst = COLOR_RESET if use_color else ""
    r_bld = COLOR_BOLD if use_color else ""
    r_cyn = COLOR_CYAN + r_bld if use_color else ""
    r_grn = COLOR_GREEN + r_bld if use_color else ""
    r_red = COLOR_RED + r_bld if use_color else ""
    r_yel = COLOR_YELLOW + r_bld if use_color else ""

    lines: list[str] = []
    lines.append("=" * 64)
    lines.append(f"{r_yel}                     QUORIDOR NO TERMINAL{r_rst}")
    lines.append("=" * 64)

    if local_player_id is not None and local_player_id in view.players:
        me = view.players[local_player_id]
        lines.append(
            f"  Servidor: {server_name or 'Local'}  |  Você é: {r_cyn}P{local_player_id} - {me['name']}{r_rst}"
        )
    else:
        lines.append("  Modo: Partida Local no Terminal")
    lines.append("=" * 64)
    lines.append("")

    # Tabuleiro centralizado
    board_lines = render_board(view, valid_moves=valid_moves, use_color=use_color)
    lines.extend(board_lines)
    lines.append("")

    # Placar dos Jogadores
    lines.append("─" * 64)
    lines.append(f"{r_bld}JOGADORES:{r_rst}")
    for pid, p in view.players.items():
        is_current = view.turn == pid and not view.winner
        is_me = local_player_id == pid
        p_color = (PLAYER_COLORS.get(pid, COLOR_RESET) + r_bld) if use_color else ""

        me_tag = " (Você)" if is_me else ""
        turn_tag = (
            f" {r_grn}[SUA VEZ]{r_rst}"
            if is_current and is_me
            else (f" {r_yel}[VEZ ATUAL]{r_rst}" if is_current else "")
        )

        target_desc = (
            f"Linha {p['target_value']}"
            if p["target_axis"] == 0
            else f"Coluna {p['target_value']}"
        )
        lines.append(
            f"  * {p_color}[P{pid}] {p['name']}{me_tag}{r_rst}: Pos {p['position']} | "
            f"Paredes: {p['remaining_walls']}/{view.walls_per_player} | Alvo: {target_desc}{turn_tag}"
        )

    lines.append("─" * 64)

    # Estado de Vencedor ou Turno
    if view.winner:
        winner_p = view.players.get(view.winner, {})
        w_name = winner_p.get("name", f"Jogador {view.winner}")
        w_color = (
            (PLAYER_COLORS.get(view.winner, COLOR_RESET) + r_bld) if use_color else ""
        )
        lines.append(
            f"{r_grn}🏆 FIM DE JOGO! O vencedor é {w_color}{w_name} (P{view.winner}){r_grn}! Parabéns! 🏆{r_rst}"
        )
        lines.append("  Digite 'r' para jogar novamente ou 'q' para sair.")
    else:
        current_p = view.players.get(view.turn, {})
        current_name = current_p.get("name", f"Jogador {view.turn}")
        is_my_turn = local_player_id is None or view.turn == local_player_id

        if is_my_turn:
            lines.append(
                f"{r_grn}>>> É A SUA VEZ DE JOGAR! ({current_name}) <<<{r_rst}"
            )
            if valid_moves:
                moves_str = ", ".join(f"({r}, {c})" for r, c in valid_moves)
                lines.append(f"  Movimentos válidos do peão: {r_cyn}{moves_str}{r_rst}")
        else:
            lines.append(
                f"  Aguardando a jogada de {r_yel}{current_name} (P{view.turn}){r_rst}..."
            )

    # Mensagens de Feedback
    if error_message:
        lines.append(f"{r_red}[!] ERRO: {error_message}{r_rst}")
    elif last_action:
        lines.append(f"{r_cyn}[*] {last_action}{r_rst}")

    # Guia Rápido de Comandos
    if not view.winner and (local_player_id is None or view.turn == local_player_id):
        lines.append("─" * 64)
        lines.append(f"{r_bld}COMANDOS DISPONÍVEIS:{r_rst}")
        lines.append(
            "  • Mover peão:      m <linha> <coluna>        (ex: m 1 4  ou simplesmente 1 4)"
        )
        lines.append(
            "  • Colocar parede:  w <linha> <coluna> <H|V>  (ex: w 3 3 H ou w 3 3 V)"
        )
        lines.append("  • Ajuda:           help                      • Sair: quit")
    lines.append("─" * 64)

    return lines


def render_lobby(
    client: QuoridorClient,
    error_message: str = "",
    use_color: bool = True,
) -> list[str]:
    """Renderiza a tela de sala de espera (lobby) no modo multiplayer."""
    r_rst = COLOR_RESET if use_color else ""
    r_bld = COLOR_BOLD if use_color else ""
    r_cyn = COLOR_CYAN + r_bld if use_color else ""
    r_grn = COLOR_GREEN + r_bld if use_color else ""
    r_yel = COLOR_YELLOW + r_bld if use_color else ""
    r_red = COLOR_RED + r_bld if use_color else ""

    state = client.get_game_state()
    lobby_players = state.get("lobby", [])
    count = len(lobby_players)
    can_start = state.get("can_start", False)

    lines: list[str] = []
    lines.append("=" * 64)
    lines.append(f"{r_yel}              SALA MULTIPLAYER - QUORIDOR (CONSOLE){r_rst}")
    lines.append("=" * 64)
    lines.append(
        f"  Servidor: {client.server_name}  |  Conectado: {r_cyn}{client.player_name} (P{client.player_id}){r_rst}"
    )
    lines.append("=" * 64)
    lines.append("")
    lines.append(f"{r_bld}JOGADORES CONECTADOS NO LOBBY ({count}/4):{r_rst}")

    for p in lobby_players:
        pid = p["id"]
        pname = p["name"]
        is_me = pid == client.player_id
        p_color = (PLAYER_COLORS.get(pid, COLOR_RESET) + r_bld) if use_color else ""
        tag = " (Você)" if is_me else ""
        lines.append(f"  * {p_color}[P{pid}] {pname}{tag}{r_rst}")

    lines.append("")
    lines.append("─" * 64)
    if can_start:
        lines.append(
            f"{r_grn}STATUS: Sala pronta para iniciar! (2 ou 4 jogadores presentes){r_rst}"
        )
        lines.append(
            f"  Comando: Digite {r_grn}'start'{r_rst} (ou 's') e pressione ENTER para começar."
        )
    else:
        lines.append(
            f"{r_yel}STATUS: Aguardando jogadores... (necessário 2 ou 4 para jogar){r_rst}"
        )

    if error_message:
        lines.append(f"{r_red}[!] ERRO: {error_message}{r_rst}")

    lines.append("  Comandos: start | quit")
    lines.append("─" * 64)
    return lines


# --- Parser de Comandos de Console ---


def parse_command(cmd_str: str) -> tuple[str, Any]:
    """Interpreta os comandos digitados pelo usuário no terminal."""
    cleaned = cmd_str.strip()
    if not cleaned:
        return ("empty", None)

    lower = cleaned.lower()

    if lower in ("q", "quit", "exit", "sair"):
        return ("quit", None)
    if lower in ("h", "help", "ajuda", "?"):
        return ("help", None)
    if lower in ("start", "s", "iniciar", "comecar"):
        return ("start", None)
    if lower in ("r", "restart", "reset", "reiniciar"):
        return ("reset", None)

    # Separa por espaços ou vírgulas
    parts = [p for p in re.split(r"[\s,]+", cleaned) if p]
    if not parts:
        return ("empty", None)

    first = parts[0].lower()

    # 1. Movimentação: 'm 1 4' ou 'move 1 4' ou diretamente '1 4'
    if first in ("m", "move", "mover") and len(parts) == 3:
        try:
            r, c = int(parts[1]), int(parts[2])
            if not (0 <= r <= 8 and 0 <= c <= 8):
                return (
                    "invalid",
                    "Coordenadas fora do limite (linhas e colunas devem ser de 0 a 8).",
                )
            return ("move", (r, c))
        except ValueError:
            return ("invalid", "Coordenadas devem ser números inteiros (ex: m 1 4).")

    # Atalho direto: '1 4' ou '1, 4'
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        r, c = int(parts[0]), int(parts[1])
        if not (0 <= r <= 8 and 0 <= c <= 8):
            return ("invalid", "Coordenadas fora do limite (0 a 8).")
        return ("move", (r, c))

    # 2. Parede: 'w 3 3 H' ou 'wall 3 3 H' ou 'p 3 3 H' ou 'parede 3 3 H'
    if first in ("w", "wall", "p", "parede") and len(parts) == 4:
        try:
            r, c = int(parts[1]), int(parts[2])
            ori = parts[3].upper()
            if not (0 <= r <= 7 and 0 <= c <= 7):
                return (
                    "invalid",
                    "Posição da parede fora dos limites (deve ser de 0 a 7 para linhas e colunas).",
                )
            if ori not in ("H", "V"):
                return (
                    "invalid",
                    "Orientação deve ser 'H' (horizontal) ou 'V' (vertical).",
                )
            return ("wall", ((r, c), ori))
        except ValueError:
            return (
                "invalid",
                "Coordenadas da parede devem ser números inteiros (ex: w 3 3 H).",
            )

    return (
        "invalid",
        "Comando não reconhecido. Use 'm <linha> <coluna>', 'w <linha> <coluna> <H|V>', ou 'quit'.",
    )


def read_line_with_event(
    prompt: str,
    cancel_event: threading.Event | None = None,
    poll_interval: float = 0.05,
) -> str | None:
    """Lê entrada do usuário permitindo cancelamento assíncrono caso cancel_event dispare."""
    sys.stdout.write(prompt)
    sys.stdout.flush()

    buf: list[str] = []

    while True:
        if cancel_event and cancel_event.is_set() and not buf:
            return None

        if HAS_MSVCRT:
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch in ("\r", "\n"):
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    return "".join(buf)
                elif ch == "\x08":  # Backspace
                    if buf:
                        buf.pop()
                        sys.stdout.write("\b \b")
                        sys.stdout.flush()
                elif ch == "\x03":  # Ctrl+C
                    raise KeyboardInterrupt
                else:
                    buf.append(ch)
                    sys.stdout.write(ch)
                    sys.stdout.flush()
            else:
                time.sleep(poll_interval)
        else:
            # Fallback seguro para ambientes não-Windows
            try:
                line = sys.stdin.readline()
                return line.strip()
            except (OSError, UnicodeDecodeError, EOFError):
                return None


# --- Loops de Execução CLI ---


def run_network_cli(client: QuoridorClient) -> None:
    """Loop principal para jogar em modo multiplayer em rede via console."""
    init_console()

    update_event = threading.Event()
    last_action_msg = ""
    error_msg = ""

    def on_network_event(event_type: str, data: Any) -> None:
        nonlocal last_action_msg
        if event_type == "state_changed" and isinstance(data, dict):
            msg = data.get("message", "")
            if msg:
                last_action_msg = msg
        elif event_type == "game_started":
            last_action_msg = "A partida foi iniciada!"
        elif event_type == "game_over" and isinstance(data, dict):
            last_action_msg = f"Fim de jogo! Vencedor: {data.get('winner_name')}"
        update_event.set()

    client.add_listener(on_network_event)

    # 1. Tela de Lobby (Aguardando início da partida)
    while True:
        state = client.get_game_state()
        if state.get("game_started"):
            break

        clear_screen()
        lobby_lines = render_lobby(client, error_message=error_msg)
        print("\n".join(lobby_lines))
        error_msg = ""

        cmd_raw = read_line_with_event(
            f"[{client.player_name}] > ", cancel_event=update_event
        )
        if cmd_raw is None:
            update_event.clear()
            continue

        cmd_type, payload = parse_command(cmd_raw)
        if cmd_type == "quit":
            client.disconnect()
            print("\nVocê saiu da sala.")
            return
        elif cmd_type == "start":
            ok, msg = client.start_game()
            if not ok:
                error_msg = msg
            else:
                update_event.set()
        elif cmd_type == "invalid":
            error_msg = payload
        elif cmd_type == "empty":
            pass

    # 2. Tela de Partida em Andamento
    running = True
    while running:
        state = client.get_game_state()
        view = extract_view_from_state(state)
        is_my_turn = view.turn == client.player_id and not view.winner
        valid_moves = client.get_valid_moves() if is_my_turn else []

        clear_screen()
        screen_lines = render_game_info(
            view=view,
            local_player_id=client.player_id,
            server_name=client.server_name,
            last_action=last_action_msg,
            error_message=error_msg,
            valid_moves=valid_moves,
        )
        print("\n".join(screen_lines))
        error_msg = ""

        if view.winner:
            cmd_raw = read_line_with_event(
                "Partida encerrada. [r] Reiniciar | [q] Sair > ",
                cancel_event=update_event,
            )
            if cmd_raw is None:
                update_event.clear()
                continue
            cmd_type, _ = parse_command(cmd_raw)
            if cmd_type == "reset":
                client.reset_game()
            elif cmd_type in ("quit", "empty"):
                break
            continue

        if is_my_turn:
            cmd_raw = read_line_with_event(
                f"[{client.player_name} (Sua vez)] > ", cancel_event=update_event
            )
            if cmd_raw is None:
                update_event.clear()
                continue

            cmd_type, payload = parse_command(cmd_raw)

            if cmd_type == "quit":
                break
            elif cmd_type == "help":
                last_action_msg = "Mover: m <linha> <coluna> (ex: m 1 4). Parede: w <linha> <coluna> <H|V> (ex: w 3 3 H)."
            elif cmd_type == "move":
                pos = payload
                if pos in valid_moves:
                    ok, msg = client.move_player(pos)
                    if not ok:
                        error_msg = msg
                    else:
                        last_action_msg = f"Você moveu para ({pos[0]}, {pos[1]})."
                else:
                    error_msg = (
                        f"Posição ({pos[0]}, {pos[1]}) não é um movimento válido!"
                    )
            elif cmd_type == "wall":
                pos, ori = payload
                ok, msg = client.place_wall(pos, ori)
                if not ok:
                    error_msg = msg
                else:
                    last_action_msg = (
                        f"Você colocou uma parede em ({pos[0]}, {pos[1]}) [{ori}]."
                    )
            elif cmd_type == "invalid":
                error_msg = payload
        else:
            # Não é a vez do cliente: aguarda notificação assíncrona do servidor
            update_event.wait(timeout=1.0)
            update_event.clear()

    client.disconnect()
    print("\nDesconectado do servidor Quoridor.")


def run_local_cli(num_players: int = 2) -> None:
    """Loop principal para jogar Quoridor localmente no terminal sem interface gráfica."""
    init_console()

    game = QuoridorGame(num_players=num_players)
    for i in range(1, num_players + 1):
        game.add_player(f"Jogador {i}")

    last_action_msg = "Partida local iniciada!"
    error_msg = ""

    while True:
        view = extract_view_from_game(game)
        current = game.players[game.turn]
        valid_moves = game.get_valid_moves(current.id) if not game.winner else []

        clear_screen()
        screen_lines = render_game_info(
            view=view,
            local_player_id=None,
            server_name="Partida Local",
            last_action=last_action_msg,
            error_message=error_msg,
            valid_moves=valid_moves,
        )
        print("\n".join(screen_lines))
        error_msg = ""

        if game.winner:
            cmd = input("\nDeseja jogar novamente? [s/n]: ").strip().lower()
            if cmd in ("s", "sim", "y", "yes", "r"):
                game = QuoridorGame(num_players=num_players)
                for i in range(1, num_players + 1):
                    game.add_player(f"Jogador {i}")
                last_action_msg = "Partida reiniciada!"
                continue
            else:
                print("Obrigado por jogar Quoridor!")
                break

        cmd_raw = input(f"[{current.name} (P{current.id})] > ")
        cmd_type, payload = parse_command(cmd_raw)

        if cmd_type == "quit":
            print("\nPartida encerrada.")
            break
        elif cmd_type == "help":
            last_action_msg = "Mover: m <linha> <coluna> (ex: m 1 4). Parede: w <linha> <coluna> <H|V> (ex: w 3 3 H)."
        elif cmd_type == "move":
            pos = payload
            if pos in valid_moves:
                ok, msg = game.move_player(current.id, pos)
                if not ok:
                    error_msg = msg
                else:
                    last_action_msg = f"{current.name} moveu para ({pos[0]}, {pos[1]})."
            else:
                error_msg = f"Posição ({pos[0]}, {pos[1]}) não é válida!"
        elif cmd_type == "wall":
            pos, ori = payload
            new_wall = Wall(pos, ori)
            ok, msg = game.place_wall(current.id, new_wall)
            if not ok:
                error_msg = msg
            else:
                last_action_msg = (
                    f"{current.name} colocou parede em ({pos[0]}, {pos[1]}) [{ori}]."
                )
        elif cmd_type == "invalid":
            error_msg = payload
