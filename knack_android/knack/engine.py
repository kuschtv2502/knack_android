"""Regel-Engine fuer das Kartenspiel Knack.

Die Engine ist absichtlich von Tkinter getrennt. Dadurch lassen sich alle
Regeln ohne grafische Oberflaeche testen und spaeter leichter anpassen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import random
from typing import Iterable, Optional


SUITS = ("Karo", "Herz", "Pik", "Kreuz")
SUIT_SYMBOLS = {"Karo": "♦", "Herz": "♥", "Pik": "♠", "Kreuz": "♣"}
RANKS = ("7", "8", "9", "10", "Bube", "Dame", "König", "Ass")
RANK_SHORT = {
    "7": "7",
    "8": "8",
    "9": "9",
    "10": "10",
    "Bube": "B",
    "Dame": "D",
    "König": "K",
    "Ass": "A",
}
CARD_VALUES = {
    "7": 7,
    "8": 8,
    "9": 9,
    "10": 10,
    "Bube": 10,
    "Dame": 10,
    "König": 10,
    "Ass": 11,
}
SUIT_STRENGTH = {suit: index for index, suit in enumerate(SUITS)}
HALF_STRENGTH = {
    "7": 0,
    "8": 1,
    "9": 2,
    "10": 3,
    "Bube": 4,
    "Dame": 5,
    "König": 6,
}

MIN_PLAYERS = 2
MAX_PLAYERS = 9
DEFAULT_STARTING_COINS = 3
MIN_STARTING_COINS = 1
MAX_STARTING_COINS = 99


class IllegalMove(ValueError):
    """Wird ausgelöst, wenn eine Aktion nach dem Regelwerk nicht erlaubt ist."""


@dataclass(frozen=True)
class Card:
    rank: str
    suit: str

    def __post_init__(self) -> None:
        if self.rank not in RANKS or self.suit not in SUITS:
            raise ValueError(f"Ungültige Karte: {self.rank} {self.suit}")

    @property
    def value(self) -> int:
        return CARD_VALUES[self.rank]

    @property
    def short(self) -> str:
        return f"{RANK_SHORT[self.rank]}{SUIT_SYMBOLS[self.suit]}"

    @property
    def long(self) -> str:
        return f"{self.rank} {self.suit}"


@dataclass(frozen=True)
class HandScore:
    """Vergleichbarer Handwert. Ein größerer Schlüssel ist besser."""

    kind: str
    value: float
    suit: str
    label: str
    key: tuple[int, float, int]


def make_deck() -> list[Card]:
    return [Card(rank, suit) for suit in SUITS for rank in RANKS]


def suit_totals(cards: Iterable[Card]) -> dict[str, int]:
    totals = {suit: 0 for suit in SUITS}
    for card in cards:
        totals[card.suit] += card.value
    return totals


def evaluate_hand(cards: Iterable[Card]) -> HandScore:
    """Wertet exakt drei Karten entsprechend dem gelieferten Regelwerk."""

    hand = list(cards)
    if len(hand) != 3:
        raise ValueError("Eine Hand muss aus genau drei Karten bestehen.")

    ranks = [card.rank for card in hand]
    highest_suit = max((card.suit for card in hand), key=SUIT_STRENGTH.get)

    # AAA ist ausdrücklich keine normale Hand und auch keine Halbe.
    if all(rank == "Ass" for rank in ranks):
        return HandScore(
            "aaa",
            0,
            highest_suit,
            "AAA (verliert, aber zahlt keine Münze)",
            (1, 0, SUIT_STRENGTH[highest_suit]),
        )

    if len(set(ranks)) == 1 and ranks[0] in HALF_STRENGTH:
        rank = ranks[0]
        label = f"Halbe {RANK_SHORT[rank]}{RANK_SHORT[rank]}{RANK_SHORT[rank]}"
        return HandScore(
            "halbe",
            30.5,
            highest_suit,
            f"{label} · {highest_suit}",
            (3, HALF_STRENGTH[rank], SUIT_STRENGTH[highest_suit]),
        )

    totals = suit_totals(hand)
    best_suit = max(SUITS, key=lambda suit: (totals[suit], SUIT_STRENGTH[suit]))
    best_value = totals[best_suit]

    if best_value == 31:
        return HandScore(
            "forbidden_31",
            31,
            best_suit,
            f"Verbotene 31 · {best_suit}",
            (0, 0, SUIT_STRENGTH[best_suit]),
        )

    return HandScore(
        "normal",
        best_value,
        best_suit,
        f"{best_value} Punkte · {best_suit}",
        (2, best_value, SUIT_STRENGTH[best_suit]),
    )


@dataclass
class Player:
    id: int
    name: str
    is_human: bool
    coins: int = 3
    hand: list[Card] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return self.coins > 0


@dataclass(frozen=True)
class RoundResult:
    reason: str
    winner_ids: tuple[int, ...]
    loser_ids: tuple[int, ...]
    payments: tuple[tuple[int, int], ...]
    scores: tuple[tuple[int, HandScore], ...]
    pot_awarded: int = 0
    jackpot_winner_id: Optional[int] = None


class KnackGame:
    """Zustandsmaschine für eine komplette Partie mit mehreren Runden."""

    def __init__(
        self,
        player_count: int = 3,
        *,
        starting_coins: int = DEFAULT_STARTING_COINS,
        rng: Optional[random.Random] = None,
        auto_deal: bool = True,
    ) -> None:
        if not MIN_PLAYERS <= player_count <= MAX_PLAYERS:
            raise ValueError(
                f"Knack wird mit {MIN_PLAYERS} bis {MAX_PLAYERS} Spielern gespielt."
            )
        if not isinstance(starting_coins, int) or not (
            MIN_STARTING_COINS <= starting_coins <= MAX_STARTING_COINS
        ):
            raise ValueError(
                f"Die Startmünzen müssen zwischen {MIN_STARTING_COINS} und "
                f"{MAX_STARTING_COINS} liegen."
            )
        self.rng = rng or random.Random()
        self.starting_coins = starting_coins
        self.players = [Player(0, "Du", True, coins=starting_coins)] + [
            Player(index, f"Computer {index}", False, coins=starting_coins)
            for index in range(1, player_count)
        ]
        self.pot = 0
        self.round_number = 0
        self.deck: list[Card] = []
        self.discard: list[Card] = []
        self.center: list[Card] = []
        self.turn_order: list[int] = []
        self.turn_pos = 0
        self.starter_id = 0
        self.pass_streak = 0
        self.closing_player_id: Optional[int] = None
        self.closing_player_ids: list[int] = []
        self.closing_remaining: Optional[int] = None
        self.round_over = True
        self.game_over = False
        self.game_winner_id: Optional[int] = None
        self.result: Optional[RoundResult] = None
        self.log: list[str] = []
        if auto_deal:
            self.start_round(initial=True)

    @property
    def active_players(self) -> list[Player]:
        return [player for player in self.players if player.active]

    @property
    def current_player_id(self) -> Optional[int]:
        if self.round_over or not self.turn_order:
            return None
        return self.turn_order[self.turn_pos]

    @property
    def current_player(self) -> Optional[Player]:
        player_id = self.current_player_id
        return None if player_id is None else self.players[player_id]

    def start_round(self, *, initial: bool = False) -> None:
        if not self.round_over:
            raise IllegalMove("Die laufende Runde muss zuerst beendet werden.")

        active_ids = [player.id for player in self.active_players]
        if len(active_ids) <= 1:
            self.game_over = True
            self.game_winner_id = active_ids[0] if active_ids else None
            return

        if not initial:
            self.starter_id = self._next_active_after(self.starter_id)
        elif self.starter_id not in active_ids:
            self.starter_id = active_ids[0]

        start_index = active_ids.index(self.starter_id)
        self.turn_order = active_ids[start_index:] + active_ids[:start_index]
        self.turn_pos = 0
        self.deck = make_deck()
        self.rng.shuffle(self.deck)
        self.discard = []
        self.center = []
        for player in self.players:
            player.hand = []
        for _ in range(3):
            for player_id in self.turn_order:
                self.players[player_id].hand.append(self.deck.pop())
        self.center = [self.deck.pop() for _ in range(3)]
        self.pass_streak = 0
        self.closing_player_id = None
        self.closing_player_ids = []
        self.closing_remaining = None
        self.round_over = False
        self.result = None
        self.round_number += 1
        self.log = [
            f"Runde {self.round_number}: {self.players[self.starter_id].name} beginnt."
        ]

    def _next_active_after(self, player_id: int) -> int:
        for offset in range(1, len(self.players) + 1):
            candidate = self.players[(player_id + offset) % len(self.players)]
            if candidate.active:
                return candidate.id
        return player_id

    def _require_turn(self, player_id: int) -> Player:
        if self.round_over:
            raise IllegalMove("Die Runde ist bereits beendet.")
        if self.current_player_id != player_id:
            raise IllegalMove("Dieser Spieler ist gerade nicht am Zug.")
        return self.players[player_id]

    def pass_turn(self, player_id: int) -> None:
        player = self._require_turn(player_id)
        self.pass_streak += 1
        self.log.append(f"{player.name} schiebt.")
        if self.closing_remaining is None and self.pass_streak >= len(self.turn_order):
            self._refresh_center()
            self.pass_streak = 0
        self._finish_action()

    def swap_one(self, player_id: int, hand_index: int, center_index: int) -> None:
        player = self._require_turn(player_id)
        if hand_index not in range(3) or center_index not in range(3):
            raise IllegalMove("Für den Einzeltausch muss je eine gültige Karte gewählt sein.")
        old_hand = player.hand[hand_index]
        old_center = self.center[center_index]
        player.hand[hand_index], self.center[center_index] = old_center, old_hand
        self.pass_streak = 0
        # Keine privaten Handkarten im gemeinsamen Rundenprotokoll verraten.
        self.log.append(f"{player.name} tauscht eine Karte.")
        self._finish_action()

    def swap_all(self, player_id: int) -> None:
        player = self._require_turn(player_id)
        old_hand = list(player.hand)
        old_center = list(self.center)
        player.hand, self.center = old_center, old_hand
        self.pass_streak = 0
        self.log.append(f"{player.name} tauscht alle drei Karten.")
        self._finish_action()

    def close(self, player_id: int) -> None:
        player = self._require_turn(player_id)
        self.pass_streak = 0
        if self.closing_remaining is None:
            self.closing_player_id = player_id
            self.closing_player_ids = [player_id]
            self.closing_remaining = len(self.turn_order) - 1
            self.log.append(
                f"{player.name} macht zu. Alle anderen haben noch genau einen Zug."
            )
            if self.closing_remaining == 0:
                self._finish_round("Zumachen")
            else:
                self._advance_turn()
            return

        if player_id in self.closing_player_ids:
            raise IllegalMove("Dieser Spieler hat bereits zugemacht.")
        self.closing_player_ids.append(player_id)
        self.log.append(f"{player.name} macht ebenfalls zu.")
        # Mit-Zumachen verbraucht nur den ohnehin letzten Zug. Die Schlussrunde
        # wird ausdrücklich nicht neu gestartet oder verlängert.
        self._finish_action()

    def can_knack(self, player_id: int) -> bool:
        player = self.players[player_id]
        # Hausregel: Für KNACK werden genau die passenden Karten betrachtet,
        # nicht automatisch alle Handkarten derselben Farbe. Das Ass muss auf
        # der Hand liegen; zusammen mit einer 10-Punkte-Handkarte ergibt es 21.
        # Eine weitere 10-Punkte-Karte derselben Farbe aus der Mitte macht 31.
        for suit in SUITS:
            ace_in_hand = any(
                card.suit == suit and card.rank == "Ass" for card in player.hand
            )
            ten_in_hand = any(
                card.suit == suit and card.value == 10 for card in player.hand
            )
            ten_in_center = any(
                card.suit == suit and card.value == 10 for card in self.center
            )
            if ace_in_hand and ten_in_hand and ten_in_center:
                return True
        return False

    def knack(self, player_id: int) -> None:
        player = self._require_turn(player_id)
        if not self.can_knack(player_id):
            raise IllegalMove(
                "Knack benötigt ein Ass und eine 10-Punkte-Karte derselben Farbe "
                "auf der Hand sowie eine weitere passende 10-Punkte-Karte in der "
                "Mitte. Die dritte Handkarte wird nicht mitgezählt."
            )
        self.log.append(f"{player.name} ruft KNACK!")
        self._finish_round("Knack", special_winner_id=player_id)

    def can_jackpot(self, player_id: int) -> bool:
        player = self.players[player_id]
        # Auslegung von „Ass, Ass, X“: genau zwei Asse plus eine Nicht-Ass-Karte.
        return (
            sum(card.rank == "Ass" for card in player.hand) == 2
            and any(card.rank == "Ass" for card in self.center)
        )

    def jackpot(self, player_id: int) -> None:
        player = self._require_turn(player_id)
        if not self.can_jackpot(player_id):
            raise IllegalMove(
                "Jackpot benötigt genau zwei Asse plus X auf der Hand und ein Ass "
                "in der Mitte."
            )
        self.log.append(f"{player.name} ruft JACKPOT!")
        self._finish_round("Jackpot", special_winner_id=player_id, jackpot=True)

    def _refresh_center(self) -> None:
        old_center = list(self.center)
        self.discard.extend(old_center)
        self.center = self._draw_cards(3)
        self.log.append("Alle haben geschoben: Die Mitte wurde vollständig erneuert.")

    def _draw_cards(self, amount: int) -> list[Card]:
        if len(self.deck) < amount and self.discard:
            self.rng.shuffle(self.discard)
            self.deck.extend(self.discard)
            self.discard = []
            self.log.append("Der Friedhof wurde gemischt und zum Nachziehstapel.")
        if len(self.deck) < amount:
            raise RuntimeError("Es sind nicht genügend Karten zum Nachziehen vorhanden.")
        return [self.deck.pop() for _ in range(amount)]

    def _finish_action(self) -> None:
        if self.closing_remaining is not None:
            self.closing_remaining -= 1
            if self.closing_remaining <= 0:
                self._finish_round("Zumachen")
                return
        self._advance_turn()

    def _advance_turn(self) -> None:
        self.turn_pos = (self.turn_pos + 1) % len(self.turn_order)

    def _finish_round(
        self,
        reason: str,
        *,
        special_winner_id: Optional[int] = None,
        jackpot: bool = False,
    ) -> None:
        scores = {player.id: evaluate_hand(player.hand) for player in self.active_players}
        candidates = [
            player
            for player in self.active_players
            if player.id != special_winner_id
        ]

        loser_ids: list[int] = []
        # Hausregel: Beim Jackpot gewinnt der Rufer nur den vorhandenen Pot.
        # Anders als bei KNACK oder einer normalen Auswertung verliert dabei
        # niemand eine Münze.
        if not jackpot and candidates:
            weakest_key = min(scores[player.id].key for player in candidates)
            loser_ids = [
                player.id for player in candidates if scores[player.id].key == weakest_key
            ]

        payments: list[tuple[int, int]] = []
        for player_id in loser_ids:
            player = self.players[player_id]
            amount = 0
            if scores[player_id].kind != "aaa" and player.coins > 0:
                player.coins -= 1
                self.pot += 1
                amount = 1
            payments.append((player_id, amount))

        if special_winner_id is not None:
            winner_ids = [special_winner_id]
        else:
            best_key = max(score.key for score in scores.values())
            winner_ids = [
                player_id for player_id, score in scores.items() if score.key == best_key
            ]

        pot_awarded = 0
        if jackpot and special_winner_id is not None:
            pot_awarded = self.pot
            self.players[special_winner_id].coins += pot_awarded
            self.pot = 0

        self.result = RoundResult(
            reason=reason,
            winner_ids=tuple(winner_ids),
            loser_ids=tuple(loser_ids),
            payments=tuple(payments),
            scores=tuple((player_id, scores[player_id]) for player_id in self.turn_order),
            pot_awarded=pot_awarded,
            jackpot_winner_id=special_winner_id if jackpot else None,
        )
        self.round_over = True
        self.current_summary_to_log()

        survivors = self.active_players
        if len(survivors) <= 1:
            self.game_over = True
            self.game_winner_id = survivors[0].id if survivors else None
            if survivors:
                self.log.append(f"{survivors[0].name} gewinnt die Partie!")
            else:
                self.log.append("Alle verbliebenen Spieler scheiden gleichzeitig aus: Remis.")

    def current_summary_to_log(self) -> None:
        if self.result is None:
            return
        self.log.append(f"Runde beendet durch: {self.result.reason}.")
        for player_id, score in self.result.scores:
            self.log.append(f"{self.players[player_id].name}: {score.label}")
        for player_id, amount in self.result.payments:
            player = self.players[player_id]
            if amount:
                self.log.append(f"{player.name} verliert 1 Münze.")
            else:
                self.log.append(f"{player.name} verliert mit AAA, zahlt aber nichts.")
        if self.result.pot_awarded:
            winner = self.players[self.result.jackpot_winner_id]  # type: ignore[index]
            self.log.append(
                f"{winner.name} erhält {self.result.pot_awarded} Münze(n) aus dem Pot."
            )

    def available_actions(self, player_id: int) -> set[str]:
        if self.current_player_id != player_id or self.round_over:
            return set()
        actions = {"pass", "swap_one", "swap_all"}
        if player_id not in self.closing_player_ids:
            actions.add("close")
        if self.can_knack(player_id):
            actions.add("knack")
        if self.can_jackpot(player_id):
            actions.add("jackpot")
        return actions


def best_exchange(
    hand: list[Card], center: list[Card]
) -> tuple[str, Optional[int], Optional[int], HandScore]:
    """Ermittelt deterministisch die beste direkte Tauschmöglichkeit für die KI."""

    current = evaluate_hand(hand)
    best: tuple[str, Optional[int], Optional[int], HandScore] = (
        "pass",
        None,
        None,
        current,
    )

    for hand_index in range(3):
        for center_index in range(3):
            candidate = list(hand)
            candidate[hand_index] = center[center_index]
            score = evaluate_hand(candidate)
            if score.key > best[3].key:
                best = ("swap_one", hand_index, center_index, score)

    all_score = evaluate_hand(center)
    if all_score.key > best[3].key:
        best = ("swap_all", None, None, all_score)
    return best
