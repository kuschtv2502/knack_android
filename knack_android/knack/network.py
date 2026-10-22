"""Einfaches, host-basiertes Direktnetzwerk für Knack (LAN oder Internet).

Das Protokoll verwendet zeilenweise JSON-Nachrichten über TCP. Der Host hält
den allein gültigen Spielzustand und prüft jeden Zug des beitretenden PCs.
"""

from __future__ import annotations

import ipaddress
import json
import queue
import socket
import threading
from typing import Any, Optional
from urllib.request import Request, urlopen

from .engine import Card, HandScore, KnackGame, RoundResult


DEFAULT_PORT = 45454


class _JsonConnection:
    def __init__(
        self,
        sock: socket.socket,
        events: "queue.Queue[dict[str, Any]]",
    ) -> None:
        self.sock = sock
        self.events = events
        self.closed = False
        self._send_lock = threading.Lock()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def send(self, message: dict[str, Any]) -> None:
        if self.closed:
            raise ConnectionError("Die Netzwerkverbindung ist geschlossen.")
        payload = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        with self._send_lock:
            self.sock.sendall(payload)

    def _read_loop(self) -> None:
        buffer = b""
        try:
            while not self.closed:
                chunk = self.sock.recv(65536)
                if not chunk:
                    break
                buffer += chunk
                if len(buffer) > 1_000_000:
                    self.events.put(
                        {"event": "error", "message": "Netzwerknachricht ist zu groß."}
                    )
                    break
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line:
                        continue
                    try:
                        message = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        self.events.put(
                            {"event": "error", "message": "Ungültige Netzwerknachricht."}
                        )
                        continue
                    self.events.put({"event": "message", "message": message})
        except OSError as exc:
            if not self.closed:
                self.events.put({"event": "error", "message": str(exc)})
        finally:
            was_open = not self.closed
            self.close()
            if was_open:
                self.events.put({"event": "disconnected"})

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


class LanHost:
    def __init__(self, port: int = DEFAULT_PORT) -> None:
        self.port = port
        self.events: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self.listener: Optional[socket.socket] = None
        self.connection: Optional[_JsonConnection] = None
        self.closed = False

    def start(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("0.0.0.0", self.port))
        self.port = int(listener.getsockname()[1])
        listener.listen(1)
        listener.settimeout(0.5)
        self.listener = listener
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def discover_public_ip(self) -> None:
        threading.Thread(target=self._public_ip_worker, daemon=True).start()

    def _public_ip_worker(self) -> None:
        try:
            address = public_ip_address()
        except (OSError, ValueError) as exc:
            self.events.put({"event": "public_ip_failed", "message": str(exc)})
            return
        self.events.put({"event": "public_ip", "address": address})

    def _accept_loop(self) -> None:
        assert self.listener is not None
        while not self.closed and self.connection is None:
            try:
                sock, address = self.listener.accept()
            except socket.timeout:
                continue
            except OSError as exc:
                if not self.closed:
                    self.events.put({"event": "error", "message": str(exc)})
                return
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.connection = _JsonConnection(sock, self.events)
            self.events.put({"event": "connected", "address": address[0]})
            return

    def send(self, message: dict[str, Any]) -> None:
        if self.connection is None:
            raise ConnectionError("Noch kein Mitspieler verbunden.")
        self.connection.send(message)

    def close(self) -> None:
        self.closed = True
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        if self.listener is not None:
            try:
                self.listener.close()
            except OSError:
                pass
            self.listener = None


class LanClient:
    def __init__(self) -> None:
        self.events: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self.connection: Optional[_JsonConnection] = None
        self.closed = False

    def connect(self, host: str, port: int = DEFAULT_PORT) -> None:
        threading.Thread(
            target=self._connect_worker,
            args=(host, port),
            daemon=True,
        ).start()

    def _connect_worker(self, host: str, port: int) -> None:
        try:
            sock = socket.create_connection((host, port), timeout=6)
            sock.settimeout(None)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError as exc:
            self.events.put({"event": "connect_failed", "message": str(exc)})
            return
        if self.closed:
            sock.close()
            return
        self.connection = _JsonConnection(sock, self.events)
        self.events.put({"event": "connected"})

    def send(self, message: dict[str, Any]) -> None:
        if self.connection is None:
            raise ConnectionError("Keine Verbindung zum Host.")
        self.connection.send(message)

    def close(self) -> None:
        self.closed = True
        if self.connection is not None:
            self.connection.close()
            self.connection = None


def local_ip_address() -> str:
    """Ermittelt die übliche LAN-IP ohne tatsächlich Daten zu senden."""

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        probe.close()


def public_ip_address() -> str:
    """Liest beim Eröffnen die öffentliche IPv4-Adresse des Host-Netzes."""

    request = Request(
        "https://api.ipify.org",
        headers={"User-Agent": "Knack-Kartenspiel/1.0"},
    )
    with urlopen(request, timeout=5) as response:
        address = response.read(64).decode("ascii").strip()
    parsed = ipaddress.ip_address(address)
    if parsed.version != 4:
        raise ValueError("Keine öffentliche IPv4-Adresse ermittelt.")
    return str(parsed)


def _card_data(card: Card) -> dict[str, str]:
    return {"rank": card.rank, "suit": card.suit}


def _card_from_data(data: dict[str, str]) -> Card:
    return Card(data["rank"], data["suit"])


def game_snapshot(game: KnackGame, viewer_id: int) -> dict[str, Any]:
    """Erzeugt einen gefilterten Zustand; fremde Hände bleiben bis Rundenende geheim."""

    players = []
    for player in game.players:
        visible = game.round_over or player.id == viewer_id
        players.append(
            {
                "id": player.id,
                "name": player.name,
                "coins": player.coins,
                "hand_count": len(player.hand),
                "hand": [_card_data(card) for card in player.hand] if visible else [],
            }
        )

    result: Optional[dict[str, Any]] = None
    if game.result is not None:
        result = {
            "reason": game.result.reason,
            "winner_ids": list(game.result.winner_ids),
            "loser_ids": list(game.result.loser_ids),
            "payments": [list(item) for item in game.result.payments],
            "scores": [
                {
                    "player_id": player_id,
                    "kind": score.kind,
                    "value": score.value,
                    "suit": score.suit,
                    "label": score.label,
                    "key": list(score.key),
                }
                for player_id, score in game.result.scores
            ],
            "pot_awarded": game.result.pot_awarded,
            "jackpot_winner_id": game.result.jackpot_winner_id,
        }

    return {
        "type": "state",
        "viewer_id": viewer_id,
        "players": players,
        "starting_coins": game.starting_coins,
        "pot": game.pot,
        "round_number": game.round_number,
        "center": [_card_data(card) for card in game.center],
        "discard": [_card_data(card) for card in game.discard],
        "turn_order": list(game.turn_order),
        "turn_pos": game.turn_pos,
        "starter_id": game.starter_id,
        "pass_streak": game.pass_streak,
        "closing_player_id": game.closing_player_id,
        "closing_player_ids": list(game.closing_player_ids),
        "closing_remaining": game.closing_remaining,
        "round_over": game.round_over,
        "game_over": game.game_over,
        "game_winner_id": game.game_winner_id,
        "result": result,
        "log": list(game.log),
    }


def game_from_snapshot(data: dict[str, Any]) -> KnackGame:
    """Baut auf dem Gast-PC eine reine Anzeige-Kopie des Host-Zustands."""

    game = KnackGame(
        len(data["players"]),
        starting_coins=int(data.get("starting_coins", 3)),
        auto_deal=False,
    )
    for player_data in data["players"]:
        player = game.players[int(player_data["id"])]
        player.name = str(player_data["name"])
        player.coins = int(player_data["coins"])
        player.is_human = True
        player.hand = [_card_from_data(card) for card in player_data["hand"]]
        # Bei fremden Spielern bleibt die Hand während der Runde absichtlich
        # leer. Die Oberfläche benötigt trotzdem die Anzahl, um genau so viele
        # Kartenrückseiten anzuzeigen. Player verwendet keine Slots, daher kann
        # diese reine Netzwerkansicht gefahrlos am Spiegelobjekt gespeichert werden.
        player.hand_count = int(player_data.get("hand_count", len(player.hand)))

    game.pot = int(data["pot"])
    game.round_number = int(data["round_number"])
    game.center = [_card_from_data(card) for card in data["center"]]
    game.discard = [_card_from_data(card) for card in data.get("discard", [])]
    game.turn_order = [int(value) for value in data["turn_order"]]
    game.turn_pos = int(data["turn_pos"])
    game.starter_id = int(data["starter_id"])
    game.pass_streak = int(data["pass_streak"])
    game.closing_player_id = data["closing_player_id"]
    game.closing_player_ids = [
        int(value)
        for value in data.get(
            "closing_player_ids",
            [] if game.closing_player_id is None else [game.closing_player_id],
        )
    ]
    game.closing_remaining = data["closing_remaining"]
    game.round_over = bool(data["round_over"])
    game.game_over = bool(data["game_over"])
    game.game_winner_id = data["game_winner_id"]
    game.log = [str(line) for line in data["log"]]

    result_data = data.get("result")
    if result_data is not None:
        scores = []
        for item in result_data["scores"]:
            score = HandScore(
                kind=item["kind"],
                value=float(item["value"]),
                suit=item["suit"],
                label=item["label"],
                key=(int(item["key"][0]), float(item["key"][1]), int(item["key"][2])),
            )
            scores.append((int(item["player_id"]), score))
        game.result = RoundResult(
            reason=result_data["reason"],
            winner_ids=tuple(int(value) for value in result_data["winner_ids"]),
            loser_ids=tuple(int(value) for value in result_data["loser_ids"]),
            payments=tuple(
                (int(item[0]), int(item[1])) for item in result_data["payments"]
            ),
            scores=tuple(scores),
            pot_awarded=int(result_data["pot_awarded"]),
            jackpot_winner_id=result_data["jackpot_winner_id"],
        )
    return game
