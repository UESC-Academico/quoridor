from __future__ import annotations

import os
import threading
from typing import TYPE_CHECKING, Any

from core.game import QuoridorGame
from core.models import Wall

if TYPE_CHECKING:
    from network.client import QuoridorClient


def limpar_tela() -> None:
    """Limpa o console para manter o tabuleiro sempre visível no topo."""
    os.system("cls" if os.name == "nt" else "clear")


def imprimir_tabuleiro(
    players: dict[int, dict[str, Any]],
    walls: set[tuple[tuple[int, int], str]],
    turn: int,
    winner: int | None = None,
    my_id: int | None = None,
) -> None:
    """Desenha a matriz 9x9 do Quoridor, peões (P1..P4) e paredes no terminal."""
    # Mapeia posição (r, c) para o ID do jogador (apenas jogadores ativos)
    posicoes_peoes = {
        tuple(p["pos"]): pid for pid, p in players.items() if p.get("is_active", True)
    }

    print("\n    0   1   2   3   4   5   6   7   8")
    print("  +" + "---+" * 9)

    for r in range(9):
        # 1. Linha com as células e peões
        linha_celulas = f"{r} |"
        for c in range(9):
            if (r, c) in posicoes_peoes:
                linha_celulas += f"P{posicoes_peoes[(r, c)]} "
            else:
                linha_celulas += " . "

            # Divisória vertical: verifica se há parede vertical à direita
            parede_v = ((r, c), "V") in walls or ((r - 1, c), "V") in walls
            linha_celulas += "#" if parede_v else "|"

        print(f"{linha_celulas} {r}")

        # 2. Linha divisória horizontal entre linhas (apenas até a linha 7)
        if r < 8:
            linha_divisoria = "  +"
            for c in range(9):
                # Parede horizontal abaixo da célula (r, c)
                parede_h = ((r, c), "H") in walls or ((r, c - 1), "H") in walls
                linha_divisoria += "===" if parede_h else "---"
                linha_divisoria += "+"
            print(linha_divisoria)

    print("  +" + "---+" * 9)
    print("    0   1   2   3   4   5   6   7   8")

    # Placar e status
    print("\n--- Jogadores ---")
    for pid, p in players.items():
        if not p.get("is_active", True):
            print(f"  P{pid} - {p['name']}: [DESCONECTADO / ELIMINADO]")
            continue

        marcador_vez = (
            " [SUA VEZ]" if pid == turn and not winner and pid == my_id else ""
        )
        if not marcador_vez and pid == turn and not winner:
            marcador_vez = " [VEZ ATUAL]"
        tag_voce = " (Você)" if pid == my_id else ""
        print(
            f"  P{pid} - {p['name']}{tag_voce}: Pos {p['pos']} | "
            f"Paredes restantes: {p['walls']}{marcador_vez}"
        )


def processar_comando(texto: str) -> tuple[str, Any]:
    """Interpreta os comandos digitados pelo jogador."""
    partes = texto.strip().split()
    if not partes:
        return "vazio", None

    cmd = partes[0].lower()
    if cmd in ("sair", "quit", "q"):
        return "sair", None
    if cmd in ("iniciar", "start", "s"):
        return "iniciar", None

    # Mover: 'm 1 4' ou '1 4'
    if (cmd in ("m", "mover") and len(partes) == 3) or (
        len(partes) == 2 and partes[0].isdigit() and partes[1].isdigit()
    ):
        try:
            r = int(partes[1]) if cmd in ("m", "mover") else int(partes[0])
            c = int(partes[2]) if cmd in ("m", "mover") else int(partes[1])
            if 0 <= r <= 8 and 0 <= c <= 8:
                return "mover", (r, c)
            return "invalido", "Coordenadas devem estar entre 0 e 8."
        except ValueError:
            return "invalido", "As coordenadas devem ser números inteiros."

    # Parede: 'w 3 3 H' ou 'p 3 3 V'
    if cmd in ("w", "p", "parede") and len(partes) == 4:
        try:
            r, c = int(partes[1]), int(partes[2])
            ori = partes[3].upper()
            if not (0 <= r <= 7 and 0 <= c <= 7):
                return "invalido", "Posição da parede deve estar entre 0 e 7."
            if ori not in ("H", "V"):
                return (
                    "invalido",
                    "Orientação deve ser 'H' (horizontal) ou 'V' (vertical).",
                )
            return "parede", ((r, c), ori)
        except ValueError:
            return "invalido", "As coordenadas devem ser números inteiros."

    return (
        "invalido",
        "Comando inválido! Use 'm linha col' para mover ou 'w linha col H/V' para parede.",
    )


def run_local_cli(num_players: int = 2) -> None:
    """Loop principal para uma partida local no console."""
    game = QuoridorGame(num_players=num_players)
    for i in range(1, num_players + 1):
        game.add_player(f"Jogador {i}")

    mensagem_acao = "Partida local iniciada!"

    while True:
        limpar_tela()
        print(f"=== QUORIDOR (MODO LOCAL - {num_players} JOGADORES) ===")

        players_data = {
            pid: {"name": p.name, "pos": tuple(p.position), "walls": p.remaining_walls}
            for pid, p in game.players.items()
        }
        walls_data = {(tuple(w.position), w.orientation) for w in game.walls}

        imprimir_tabuleiro(players_data, walls_data, game.turn, game.winner)

        if mensagem_acao:
            print(f"\n[*] {mensagem_acao}")
            mensagem_acao = ""

        if game.winner:
            vencedor = game.players[game.winner].name
            print(f"\n🏆 Fim de jogo! O Jogador {game.winner} ({vencedor}) venceu!")
            break

        atual = game.players[game.turn]
        validos = game.get_valid_moves(atual.id)
        print("Movimentos válidos:", ", ".join(f"({r},{c})" for r, c in validos))

        try:
            cmd_str = input(f"\n[{atual.name} (P{atual.id})] > ")
        except (KeyboardInterrupt, EOFError):
            print("\nPartida encerrada.")
            break

        tipo, dados = processar_comando(cmd_str)

        if tipo == "sair":
            print("\nPartida encerrada.")
            break
        elif tipo == "mover":
            _, msg = game.move_player(atual.id, dados)
            mensagem_acao = msg
        elif tipo == "parede":
            pos, ori = dados
            _, msg = game.place_wall(atual.id, Wall(pos, ori))
            mensagem_acao = msg
        elif tipo == "invalido":
            mensagem_acao = f"Erro: {dados}"


def run_network_cli(client: QuoridorClient) -> None:
    """Loop principal para partida multiplayer via Pyro5 no console."""
    update_event = threading.Event()
    client.add_listener(lambda event, data: update_event.set())

    mensagem_acao = ""

    # 1. Sala de Espera (Lobby)
    while True:
        state = client.get_game_state()
        if state.get("game_started"):
            break

        limpar_tela()
        print(f"=== SALA MULTIPLAYER - {client.server_name} ===")
        print(
            f"Você está conectado como: {client.player_name} (ID: {client.player_id})\n"
        )

        lobby = state.get("lobby", [])
        print(f"Jogadores conectados ({len(lobby)}/4):")
        for p in lobby:
            tag_voce = " (Você)" if p["id"] == client.player_id else ""
            print(f"  * P{p['id']}: {p['name']}{tag_voce}")

        if state.get("can_start"):
            print("\n[OK] A sala pode ser iniciada! Digite 'start' para começar.")
        else:
            print("\nAguardando mais jogadores (mínimo de 2 ou 4)...")
            print("(Pressione ENTER para atualizar a lista ou digite 'sair')")

        if mensagem_acao:
            print(f"\n[*] {mensagem_acao}")
            mensagem_acao = ""

        try:
            cmd_str = input(f"\n[{client.player_name}] > ")
        except (KeyboardInterrupt, EOFError):
            client.disconnect()
            return

        tipo, _ = processar_comando(cmd_str)
        if tipo == "sair":
            client.disconnect()
            print("\nVocê saiu da sala.")
            return
        elif tipo == "iniciar":
            ok, msg = client.start_game()
            if not ok:
                mensagem_acao = f"Erro: {msg}"

    # 2. Partida em Andamento
    while True:
        state = client.get_game_state()
        if not state.get("game_started"):
            break

        limpar_tela()
        print(f"=== QUORIDOR MULTIPLAYER - {client.server_name} ===")

        players_data = {
            int(pid): {
                "name": p["name"],
                "pos": tuple(p["position"]),
                "walls": p["remaining_walls"],
                "is_active": p.get("is_active", True),
            }
            for pid, p in state.get("players", {}).items()
        }
        walls_data = {
            (tuple(w["position"]), w["orientation"]) for w in state.get("walls", [])
        }
        turn = state.get("turn", 1)
        winner = state.get("winner")

        imprimir_tabuleiro(
            players_data, walls_data, turn, winner, my_id=client.player_id
        )

        if mensagem_acao:
            print(f"\n[*] {mensagem_acao}")
            mensagem_acao = ""

        if winner:
            vencedor = players_data.get(winner, {}).get("name", f"Jogador {winner}")
            print(f"\n🏆 Fim de jogo! O vencedor é {vencedor} (P{winner})!")
            break

        if turn == client.player_id:
            # Vez do jogador local
            validos = client.get_valid_moves()
            if validos:
                print(
                    "Movimentos válidos:", ", ".join(f"({r},{c})" for r, c in validos)
                )

            try:
                cmd_str = input(f"\n[{client.player_name} (Sua vez)] > ")
            except (KeyboardInterrupt, EOFError):
                break

            tipo, dados = processar_comando(cmd_str)
            if tipo == "sair":
                break
            elif tipo == "mover":
                _, msg = client.move_player(dados)
                mensagem_acao = msg
            elif tipo == "parede":
                pos, ori = dados
                _, msg = client.place_wall(pos, ori)
                mensagem_acao = msg
            elif tipo == "invalido":
                mensagem_acao = f"Erro: {dados}"
        else:
            # Vez do adversário: aguarda callback do servidor
            jogador_vez = players_data.get(turn, {}).get("name", f"Jogador {turn}")
            print(f"\nAguardando a jogada de {jogador_vez} (P{turn})...")
            update_event.wait(timeout=2.0)
            update_event.clear()

    client.disconnect()
    print("\nDesconectado do servidor.")
