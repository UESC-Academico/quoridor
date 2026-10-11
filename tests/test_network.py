import time
import threading
import unittest
import Pyro5.api
from network.config import configure_pyro
from network.server import QuoridorServer, start_server
from network.client import QuoridorClient


class TestQuoridorNetwork(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configure_pyro()
        cls.ns_port = 9095
        cls.server_name = "test.quoridor.servidor"
        cls.daemon, cls.server_instance, cls.ns_thread = start_server(
            server_name=cls.server_name,
            host="localhost",
            port=0,
            ns_host="localhost",
            ns_port=cls.ns_port,
            auto_start_ns=True,
        )
        cls.daemon_thread = threading.Thread(
            target=cls.daemon.requestLoop,
            daemon=True,
            name="ServerDaemonThread"
        )
        cls.daemon_thread.start()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.daemon.shutdown()
        except Exception:
            pass

    def setUp(self):
        # Reinicia o estado do servidor entre os testes
        self.server_instance.game = None
        self.server_instance.lobby.clear()
        self.server_instance.callbacks.clear()

    def test_single_instance_behavior(self):
        """Verifica se o servidor foi decorado com instance_mode='single'."""
        self.assertEqual(QuoridorServer._pyroInstancing, ("single", None))

    def test_lobby_limits_and_start_conditions(self):
        """Testa o gerenciamento de sala:

        - Máximo de 4 jogadores no lobby
        - Início apenas com 2 ou 4 jogadores (falha com 1 ou 3)
        """
        c1 = QuoridorClient(
            "Jogador 1",
            server_name=self.server_name,
            callback_host="localhost",
            ns_port=self.ns_port
        )
        res1 = c1.connect()
        self.assertEqual(res1["player_id"], 1)

        # Tentativa de iniciar com apenas 1 jogador deve falhar
        started, msg = c1.start_game()
        self.assertFalse(started)
        self.assertIn("2 ou 4", msg)

        # Conecta jogador 2
        c2 = QuoridorClient(
            "Jogador 2",
            server_name=self.server_name,
            callback_host="localhost",
            ns_port=self.ns_port
        )
        res2 = c2.connect()
        self.assertEqual(res2["player_id"], 2)

        # Conecta jogador 3
        c3 = QuoridorClient(
            "Jogador 3",
            server_name=self.server_name,
            callback_host="localhost",
            ns_port=self.ns_port
        )
        res3 = c3.connect()
        self.assertEqual(res3["player_id"], 3)

        # Tentativa de iniciar com 3 jogadores deve falhar
        started, msg = c1.start_game()
        self.assertFalse(started)
        self.assertIn("2 ou 4", msg)

        # Conecta jogador 4
        c4 = QuoridorClient(
            "Jogador 4",
            server_name=self.server_name,
            callback_host="localhost",
            ns_port=self.ns_port
        )
        res4 = c4.connect()
        self.assertEqual(res4["player_id"], 4)

        # Tentativa de conectar 5º jogador deve falhar (máximo 4)
        c5 = QuoridorClient(
            "Jogador 5",
            server_name=self.server_name,
            callback_host="localhost",
            ns_port=self.ns_port
        )
        with self.assertRaises(Exception) as ctx:
            c5.connect()
        self.assertIn("cheio", str(ctx.exception).lower())

        c1.disconnect()
        c2.disconnect()
        c3.disconnect()
        c4.disconnect()
        c5.disconnect()

    def test_bidirectional_callbacks_and_turns(self):
        """Testa comunicação bidirecional com callbacks assíncronos (oneway)

        e sincronização de movimentos em partida de 2 jogadores.
        """
        events_p1 = []
        events_p2 = []

        c1 = QuoridorClient("Alice", server_name=self.server_name, ns_port=self.ns_port)
        c2 = QuoridorClient("Bob", server_name=self.server_name, ns_port=self.ns_port)

        c1.add_listener(lambda ev, data: events_p1.append((ev, data)))
        c2.add_listener(lambda ev, data: events_p2.append((ev, data)))

        c1.connect()
        c2.connect()

        # Inicia partida de 2 jogadores
        started, msg = c1.start_game()
        self.assertTrue(started)
        time.sleep(0.3)

        # Ambos os jogadores devem ter recebido 'game_started' via callback
        p1_started = any(e[0] == "game_started" for e in events_p1)
        p2_started = any(e[0] == "game_started" for e in events_p2)
        self.assertTrue(p1_started)
        self.assertTrue(p2_started)

        # Vez do jogador 1 (Alice na posição inicial (0, 4))
        # Jogador 2 tenta jogar fora de hora -> deve falhar
        ok, reason = c2.move_player((7, 4))
        self.assertFalse(ok)
        self.assertIn("Não é a sua vez", reason)

        # Jogador 1 move peão para frente (1, 4)
        valid_moves_p1 = c1.get_valid_moves()
        self.assertIn((1, 4), valid_moves_p1)

        ok, reason = c1.move_player((1, 4))
        self.assertTrue(ok)
        time.sleep(0.3)

        # Jogador 2 deve ter recebido a atualização de estado via callback
        state_p2 = c2.get_game_state()
        self.assertEqual(state_p2["turn"], 2)
        self.assertEqual(tuple(state_p2["players"][1]["position"]), (1, 4))

        # Agora é a vez do Jogador 2: coloca uma parede horizontal válida
        ok, reason = c2.place_wall((3, 3), "H")
        self.assertTrue(ok)
        time.sleep(0.3)

        state_p1 = c1.get_game_state()
        self.assertEqual(state_p1["turn"], 1)
        self.assertEqual(len(state_p1["walls"]), 1)
        self.assertEqual(tuple(state_p1["walls"][0]["position"]), (3, 3))
        self.assertEqual(state_p1["walls"][0]["orientation"], "H")

        c1.disconnect()
        c2.disconnect()

    def test_concurrency_lock_protection(self):
        """Verifica se múltiplas chamadas simultâneas são protegidas pelo lock do servidor."""
        c1 = QuoridorClient("Speedy1", server_name=self.server_name, ns_port=self.ns_port)
        c2 = QuoridorClient("Speedy2", server_name=self.server_name, ns_port=self.ns_port)
        c1.connect()
        c2.connect()
        c1.start_game()

        # Executa múltiplas threads simultâneas lendo e verificando estado
        errors = []

        def worker(client):
            try:
                for _ in range(20):
                    _ = client.get_game_state()
                    _ = client.get_valid_moves()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker, args=(c1,)),
            threading.Thread(target=worker, args=(c2,)),
            threading.Thread(target=worker, args=(c1,)),
            threading.Thread(target=worker, args=(c2,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)

        c1.disconnect()
        c2.disconnect()

    def test_four_players_game(self):
        """Testa partida completa com 4 jogadores:

        - 4 jogadores conectam no lobby
        - Partida inicia com 4 jogadores e 5 paredes por jogador
        - Rotação de turnos: P1 -> P2 -> P3 -> P4 -> P1
        """
        clients = [
            QuoridorClient(f"Player_{i}", server_name=self.server_name, ns_port=self.ns_port)
            for i in range(1, 5)
        ]
        for c in clients:
            c.connect()

        started, msg = clients[0].start_game()
        self.assertTrue(started)
        time.sleep(0.3)

        state = clients[0].get_game_state()
        self.assertEqual(state["num_players"], 4)
        self.assertEqual(state["walls_per_player"], 5)
        self.assertEqual(len(state["players"]), 4)

        # Rotação de turnos
        # P1 na posição inicial (0, 4) move para (1, 4)
        ok, _ = clients[0].move_player((1, 4))
        self.assertTrue(ok)
        time.sleep(0.2)
        self.assertEqual(clients[1].get_game_state()["turn"], 2)

        # P2 na posição inicial (8, 4) move para (7, 4)
        ok, _ = clients[1].move_player((7, 4))
        self.assertTrue(ok)
        time.sleep(0.2)
        self.assertEqual(clients[2].get_game_state()["turn"], 3)

        # P3 na posição inicial (4, 0) move para (4, 1)
        ok, _ = clients[2].move_player((4, 1))
        self.assertTrue(ok)
        time.sleep(0.2)
        self.assertEqual(clients[3].get_game_state()["turn"], 4)

        # P4 na posição inicial (4, 8) move para (4, 7)
        ok, _ = clients[3].move_player((4, 7))
        self.assertTrue(ok)
        time.sleep(0.2)
        self.assertEqual(clients[0].get_game_state()["turn"], 1)

        for c in clients:
            c.disconnect()

    def test_game_over_callback_and_reset(self):
        """Testa transmissão de game over e reinício de partida."""
        c1 = QuoridorClient("Hero", server_name=self.server_name, ns_port=self.ns_port)
        c2 = QuoridorClient("Rival", server_name=self.server_name, ns_port=self.ns_port)

        game_over_events = []
        c2.add_listener(lambda ev, data: game_over_events.append((ev, data)) if ev == "game_over" else None)

        c1.connect()
        c2.connect()
        c1.start_game()
        time.sleep(0.2)

        # Simula vitória: define a posição de P1 a um passo da linha 8 em uma coluna livre
        with self.server_instance.lock:
            self.server_instance.game.players[1].position = (7, 3)

        # P1 move para a linha 8 (8, 3) (vitória!)
        ok, msg = c1.move_player((8, 3))
        self.assertTrue(ok, f"Movimento deveria ser válido mas retornou: {msg}")
        time.sleep(0.3)

        state = c1.get_game_state()
        self.assertEqual(state["winner"], 1)
        self.assertTrue(len(game_over_events) >= 1)
        self.assertEqual(game_over_events[0][1]["winner_id"], 1)

        # Reinicia o jogo
        ok_reset, _ = c1.reset_game()
        self.assertTrue(ok_reset)
        time.sleep(0.2)

        state_reset = c2.get_game_state()
        self.assertFalse(state_reset["game_started"])
        self.assertIsNone(state_reset["winner"])

        c1.disconnect()
        c2.disconnect()


if __name__ == "__main__":
    unittest.main()

