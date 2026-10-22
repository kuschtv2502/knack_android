import time
import unittest

from knack.engine import IllegalMove, KnackGame
from knack.lobby import LobbyServer
from knack.mobile_controller import MobileController


def wait_until(predicate, controllers, timeout=4.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for controller in controllers:
            controller.poll()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Zustand wurde nicht rechtzeitig erreicht")


class LocalMobileControllerTests(unittest.TestCase):
    def test_local_game_uses_shared_engine_and_ai(self):
        controller = MobileController()
        controller.start_local("Handy", 3, 7)
        self.assertEqual(controller.game.players[0].name, "Handy")
        self.assertEqual(controller.game.players[0].coins, 7)
        controller.action("pass")
        self.assertTrue(controller.run_ai_turn())

    def test_nickname_and_limits_are_checked_by_shared_engine(self):
        controller = MobileController()
        with self.assertRaises(ValueError):
            controller.start_local("", 3, 3)
        with self.assertRaises(ValueError):
            controller.start_local("Handy", 1, 3)


class CrossplayControllerTests(unittest.TestCase):
    def setUp(self):
        self.server = LobbyServer("127.0.0.1", 0)
        self.server.start()
        self.host = MobileController()
        self.guest = MobileController()

    def tearDown(self):
        self.host.stop_network()
        self.guest.stop_network()
        self.server.close()

    def test_create_join_and_play_through_pc_compatible_protocol(self):
        self.host.connect_lobby("Android", 5, "127.0.0.1", self.server.port)
        self.guest.connect_lobby("Windows", 3, "127.0.0.1", self.server.port)
        wait_until(
            lambda: "verbunden" in self.host.status and "verbunden" in self.guest.status,
            [self.host, self.guest],
        )

        self.host.create_lobby("Crossplay-Test")
        wait_until(lambda: bool(self.host.lobby_code), [self.host, self.guest])
        self.guest.join_lobby(self.host.lobby_code)
        wait_until(
            lambda: self.host.game is not None and self.guest.game is not None,
            [self.host, self.guest],
        )

        self.assertTrue(self.host.is_host)
        self.assertTrue(self.guest.is_client)
        self.assertEqual([p.name for p in self.host.game.players], ["Android", "Windows"])
        self.assertEqual(self.guest.game.starting_coins, 5)

        self.host.action("pass")
        wait_until(lambda: self.guest.game.current_player_id == 1, [self.host, self.guest])
        self.guest.action("pass")
        wait_until(
            lambda: self.host.game.current_player_id == self.guest.game.current_player_id == 0,
            [self.host, self.guest],
        )
        self.assertEqual(self.host.game.center, self.guest.game.center)

    def test_guest_cannot_start_next_round(self):
        self.guest.network_role = "lobby_client"
        self.guest.starting_coins = 3
        self.guest.game = KnackGame(2)
        self.guest.game.round_over = True
        with self.assertRaises(IllegalMove):
            self.guest.next_round()


if __name__ == "__main__":
    unittest.main()
