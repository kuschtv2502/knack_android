import random
import unittest

from knack.engine import (
    Card,
    IllegalMove,
    KnackGame,
    best_exchange,
    evaluate_hand,
    make_deck,
)


def c(rank: str, suit: str) -> Card:
    return Card(rank, suit)


def prepared_game(hands, center, *, pot=0):
    game = KnackGame(len(hands), rng=random.Random(1), auto_deal=False)
    for player, hand in zip(game.players, hands):
        player.hand = list(hand)
    game.center = list(center)
    game.deck = make_deck()
    used = {card for hand in hands for card in hand} | set(center)
    game.deck = [card for card in game.deck if card not in used]
    game.turn_order = list(range(len(hands)))
    game.turn_pos = 0
    game.round_over = False
    game.round_number = 1
    game.pot = pot
    game.log = []
    return game


class HandEvaluationTests(unittest.TestCase):
    def test_normal_hand_counts_only_best_suit(self):
        score = evaluate_hand(
            [c("Ass", "Herz"), c("König", "Herz"), c("Ass", "Pik")]
        )
        self.assertEqual(score.kind, "normal")
        self.assertEqual(score.value, 21)
        self.assertEqual(score.suit, "Herz")

    def test_equal_points_choose_higher_suit(self):
        score = evaluate_hand([c("10", "Herz"), c("10", "Pik"), c("7", "Karo")])
        self.assertEqual(score.value, 10)
        self.assertEqual(score.suit, "Pik")

    def test_half_is_30_point_5_and_beats_normal(self):
        half = evaluate_hand([c("Dame", "Karo"), c("Dame", "Herz"), c("Dame", "Pik")])
        normal = evaluate_hand(
            [c("Ass", "Kreuz"), c("König", "Kreuz"), c("9", "Kreuz")]
        )
        self.assertEqual(half.kind, "halbe")
        self.assertEqual(half.value, 30.5)
        self.assertGreater(half.key, normal.key)

    def test_half_rank_order(self):
        kings = evaluate_hand(
            [c("König", "Karo"), c("König", "Herz"), c("König", "Pik")]
        )
        queens = evaluate_hand(
            [c("Dame", "Karo"), c("Dame", "Herz"), c("Dame", "Kreuz")]
        )
        self.assertGreater(kings.key, queens.key)

    def test_aaa_is_special_and_below_normal(self):
        aaa = evaluate_hand([c("Ass", "Karo"), c("Ass", "Herz"), c("Ass", "Pik")])
        normal = evaluate_hand([c("7", "Karo"), c("8", "Herz"), c("9", "Pik")])
        self.assertEqual(aaa.kind, "aaa")
        self.assertLess(aaa.key, normal.key)

    def test_forbidden_31_is_worst(self):
        forbidden = evaluate_hand(
            [c("Ass", "Herz"), c("König", "Herz"), c("10", "Herz")]
        )
        aaa = evaluate_hand([c("Ass", "Karo"), c("Ass", "Pik"), c("Ass", "Kreuz")])
        self.assertEqual(forbidden.kind, "forbidden_31")
        self.assertLess(forbidden.key, aaa.key)


class GameFlowTests(unittest.TestCase):
    def test_deal_is_unique_and_has_correct_sizes(self):
        game = KnackGame(4, rng=random.Random(42))
        cards = [card for player in game.players for card in player.hand] + game.center
        self.assertEqual(len(cards), 15)
        self.assertEqual(len(set(cards)), 15)
        self.assertEqual(len(game.deck), 17)

    def test_nine_players_is_the_maximum_supported_by_the_deck(self):
        game = KnackGame(9, rng=random.Random(43))
        cards = [card for player in game.players for card in player.hand] + game.center
        self.assertEqual(len(game.players), 9)
        self.assertEqual(len(cards), 30)
        self.assertEqual(len(set(cards)), 30)
        self.assertEqual(len(game.deck), 2)
        with self.assertRaises(ValueError):
            KnackGame(10)

    def test_starting_coins_are_configurable_for_every_player(self):
        game = KnackGame(5, starting_coins=7, rng=random.Random(44))
        self.assertEqual(game.starting_coins, 7)
        self.assertEqual([player.coins for player in game.players], [7] * 5)
        with self.assertRaises(ValueError):
            KnackGame(2, starting_coins=0)

    def test_single_swap_exchanges_exact_cards(self):
        game = prepared_game(
            [
                [c("7", "Karo"), c("8", "Herz"), c("9", "Pik")],
                [c("10", "Karo"), c("Bube", "Herz"), c("Dame", "Pik")],
            ],
            [c("Ass", "Kreuz"), c("König", "Kreuz"), c("7", "Kreuz")],
        )
        hand_card = game.players[0].hand[1]
        center_card = game.center[2]
        game.swap_one(0, 1, 2)
        self.assertEqual(game.players[0].hand[1], center_card)
        self.assertEqual(game.center[2], hand_card)
        self.assertEqual(game.current_player_id, 1)

    def test_all_players_passing_replaces_center(self):
        game = KnackGame(3, rng=random.Random(11))
        old_center = tuple(game.center)
        game.pass_turn(0)
        game.pass_turn(1)
        game.pass_turn(2)
        self.assertNotEqual(tuple(game.center), old_center)
        self.assertEqual(set(old_center), set(game.discard))
        self.assertEqual(game.pass_streak, 0)

    def test_close_gives_each_other_player_one_turn(self):
        game = KnackGame(3, rng=random.Random(5))
        game.close(0)
        self.assertEqual(game.current_player_id, 1)
        self.assertEqual(game.closing_remaining, 2)
        game.pass_turn(1)
        self.assertFalse(game.round_over)
        self.assertEqual(game.current_player_id, 2)
        game.pass_turn(2)
        self.assertTrue(game.round_over)

    def test_other_players_can_join_close_without_extending_round(self):
        game = KnackGame(3, rng=random.Random(5))
        game.close(0)
        self.assertEqual(game.closing_player_ids, [0])
        game.close(1)
        self.assertEqual(game.closing_player_ids, [0, 1])
        self.assertEqual(game.closing_remaining, 1)
        self.assertEqual(game.current_player_id, 2)
        game.close(2)
        self.assertTrue(game.round_over)

    def test_joining_close_does_not_restart_final_turn_counter(self):
        game = KnackGame(4, rng=random.Random(5))
        game.close(0)
        self.assertEqual(game.closing_remaining, 3)
        game.close(1)
        self.assertEqual(game.closing_remaining, 2)
        game.pass_turn(2)
        self.assertEqual(game.closing_remaining, 1)
        game.close(3)
        self.assertTrue(game.round_over)

    def test_exact_tie_makes_both_weak_players_pay(self):
        game = prepared_game(
            [
                [c("7", "Karo"), c("8", "Herz"), c("10", "Pik")],
                [c("8", "Karo"), c("7", "Herz"), c("Bube", "Pik")],
                [c("Ass", "Kreuz"), c("König", "Kreuz"), c("9", "Kreuz")],
            ],
            [c("10", "Karo"), c("Bube", "Herz"), c("Dame", "Karo")],
        )
        # Beide schwachen Hände ergeben 10 Pik und sind damit exakt gleich.
        game.close(0)
        game.pass_turn(1)
        game.pass_turn(2)
        self.assertEqual(set(game.result.loser_ids), {0, 1})
        self.assertEqual(game.players[0].coins, 2)
        self.assertEqual(game.players[1].coins, 2)
        self.assertEqual(game.pot, 2)

    def test_aaa_loser_does_not_pay(self):
        game = prepared_game(
            [
                [c("Ass", "Karo"), c("Ass", "Herz"), c("Ass", "Pik")],
                [c("7", "Kreuz"), c("8", "Kreuz"), c("9", "Kreuz")],
            ],
            [c("10", "Karo"), c("Bube", "Herz"), c("Dame", "Pik")],
        )
        game.close(0)
        game.pass_turn(1)
        self.assertEqual(game.result.loser_ids, (0,))
        self.assertEqual(game.players[0].coins, 3)
        self.assertEqual(game.pot, 0)

    def test_knack_detection_and_immediate_end(self):
        game = prepared_game(
            [
                [c("Ass", "Herz"), c("König", "Herz"), c("7", "Karo")],
                [c("7", "Kreuz"), c("8", "Kreuz"), c("9", "Kreuz")],
            ],
            [c("10", "Herz"), c("Bube", "Pik"), c("Dame", "Karo")],
        )
        self.assertTrue(game.can_knack(0))
        game.knack(0)
        self.assertTrue(game.round_over)
        self.assertEqual(game.result.reason, "Knack")
        self.assertEqual(game.result.winner_ids, (0,))
        self.assertEqual(game.players[1].coins, 2)

    def test_knack_ignores_third_same_suit_hand_card(self):
        game = prepared_game(
            [
                [c("Ass", "Herz"), c("Dame", "Herz"), c("7", "Herz")],
                [c("7", "Kreuz"), c("8", "Kreuz"), c("9", "Kreuz")],
            ],
            [c("König", "Herz"), c("8", "Pik"), c("Dame", "Karo")],
        )

        self.assertEqual(evaluate_hand(game.players[0].hand).value, 28)
        self.assertTrue(game.can_knack(0))

    def test_knack_requires_ace_on_hand_not_in_center(self):
        game = prepared_game(
            [
                [c("König", "Herz"), c("Dame", "Herz"), c("7", "Karo")],
                [c("7", "Kreuz"), c("8", "Kreuz"), c("9", "Kreuz")],
            ],
            [c("Ass", "Herz"), c("8", "Pik"), c("Dame", "Karo")],
        )

        self.assertFalse(game.can_knack(0))

    def test_new_center_after_everyone_passes_can_enable_knack(self):
        game = prepared_game(
            [
                [c("Ass", "Herz"), c("Dame", "Herz"), c("7", "Herz")],
                [c("7", "Kreuz"), c("8", "Kreuz"), c("9", "Kreuz")],
            ],
            [c("7", "Pik"), c("8", "Karo"), c("9", "Karo")],
        )
        game.deck = [c("Bube", "Karo"), c("8", "Pik"), c("König", "Herz")]

        game.pass_turn(0)
        game.pass_turn(1)

        self.assertEqual(game.current_player_id, 0)
        self.assertTrue(game.can_knack(0))
        self.assertIn("knack", game.available_actions(0))

    def test_swap_that_creates_knack_cannot_be_called_in_same_turn(self):
        game = prepared_game(
            [
                [c("Ass", "Herz"), c("König", "Herz"), c("Dame", "Herz")],
                [c("7", "Kreuz"), c("8", "Kreuz"), c("9", "Kreuz")],
            ],
            [c("7", "Karo"), c("8", "Pik"), c("Dame", "Karo")],
        )

        game.swap_one(0, 2, 0)

        self.assertEqual(game.current_player_id, 1)
        self.assertTrue(game.can_knack(0))
        self.assertEqual(game.available_actions(0), set())
        with self.assertRaises(IllegalMove):
            game.knack(0)

    def test_jackpot_awards_existing_pot_without_any_coin_loss(self):
        game = prepared_game(
            [
                [c("Ass", "Karo"), c("Ass", "Herz"), c("7", "Karo")],
                [c("8", "Kreuz"), c("9", "Kreuz"), c("10", "Kreuz")],
            ],
            [c("Ass", "Pik"), c("Bube", "Pik"), c("Dame", "Karo")],
            pot=4,
        )
        self.assertTrue(game.can_jackpot(0))
        game.jackpot(0)
        self.assertEqual(game.result.pot_awarded, 4)
        self.assertEqual(game.result.loser_ids, ())
        self.assertEqual(game.result.payments, ())
        self.assertEqual(game.players[0].coins, 7)
        self.assertEqual(game.players[1].coins, 3)
        self.assertEqual(game.pot, 0)

    def test_three_aces_do_not_count_as_jackpot(self):
        game = prepared_game(
            [
                [c("Ass", "Karo"), c("Ass", "Herz"), c("Ass", "Kreuz")],
                [c("8", "Kreuz"), c("9", "Kreuz"), c("10", "Kreuz")],
            ],
            [c("Ass", "Pik"), c("Bube", "Pik"), c("Dame", "Karo")],
        )
        self.assertFalse(game.can_jackpot(0))

    def test_best_exchange_avoids_forbidden_31_and_improves_hand(self):
        hand = [c("Ass", "Herz"), c("König", "Herz"), c("10", "Herz")]
        center = [c("9", "Herz"), c("7", "Karo"), c("8", "Pik")]
        action, hand_index, center_index, score = best_exchange(hand, center)
        self.assertEqual(action, "swap_one")
        self.assertNotEqual(score.kind, "forbidden_31")
        self.assertIsNotNone(hand_index)
        self.assertIsNotNone(center_index)


if __name__ == "__main__":
    unittest.main()
