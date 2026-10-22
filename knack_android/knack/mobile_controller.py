"""UI-unabhängige Steuerung für die Android-Version von Knack.

Die Klasse spricht exakt dasselbe Lobby- und Spielprotokoll wie die
Tkinter-PC-Version. Kivy greift nur auf diese Steuerung zu und enthält selbst
keine Spielregeln.
"""

from __future__ import annotations

import queue
from typing import Any, Optional

from .engine import (
    IllegalMove,
    KnackGame,
    best_exchange,
    evaluate_hand,
)
from .lobby import DEFAULT_LOBBY_HOST, DEFAULT_LOBBY_PORT, LobbyClient
from .network import game_from_snapshot, game_snapshot


class MobileController:
    """Verbindet lokale Partien, Online-Lobbys und eine beliebige Oberfläche."""

    def __init__(self) -> None:
        self.game: Optional[KnackGame] = None
        self.nickname = "Spieler"
        self.starting_coins = 3
        self.local_player_id = 0
        self.network_role: Optional[str] = None
        self.lobby_client: Optional[LobbyClient] = None
        self.lobbies: list[dict[str, Any]] = []
        self.lobby_code = ""
        self.awaiting_network = False
        self.status = ""

    @property
    def online(self) -> bool:
        return self.network_role in {"lobby_browser", "lobby_host", "lobby_client"}

    @property
    def is_host(self) -> bool:
        return self.network_role == "lobby_host"

    @property
    def is_client(self) -> bool:
        return self.network_role == "lobby_client"

    @staticmethod
    def clean_nickname(value: str) -> str:
        return "".join(character for character in value.strip() if character.isprintable())[:20]

    def start_local(self, nickname: str, players: int, starting_coins: int) -> None:
        self.stop_network()
        nickname = self.clean_nickname(nickname)
        if not nickname:
            raise ValueError("Bitte einen Nickname eingeben.")
        self.nickname = nickname
        self.starting_coins = int(starting_coins)
        self.local_player_id = 0
        self.game = KnackGame(int(players), starting_coins=self.starting_coins)
        self.game.players[0].name = nickname
        self.status = "Lokale Partie gestartet."

    def connect_lobby(
        self,
        nickname: str,
        starting_coins: int,
        host: str = DEFAULT_LOBBY_HOST,
        port: int = DEFAULT_LOBBY_PORT,
    ) -> None:
        self.stop_network()
        nickname = self.clean_nickname(nickname)
        if not nickname:
            raise ValueError("Bitte einen Nickname eingeben.")
        self.nickname = nickname
        self.starting_coins = int(starting_coins)
        self.network_role = "lobby_browser"
        self.lobby_client = LobbyClient()
        self.status = f"Verbinde mit {host}:{port} …"
        self.lobby_client.connect(host, port)

    def create_lobby(self, name: str) -> None:
        name = name.strip()[:30]
        if not name:
            raise ValueError("Bitte einen Lobbynamen eingeben.")
        self._send({"type": "create_lobby", "name": name})

    def join_lobby(self, code: str) -> None:
        if not code:
            raise ValueError("Bitte zuerst eine freie Lobby auswählen.")
        self._send({"type": "join_lobby", "code": code})

    def refresh_lobbies(self) -> None:
        self._send({"type": "list_lobbies"})

    def leave_to_menu(self) -> None:
        self.stop_network()
        self.game = None
        self.status = ""

    def stop_network(self) -> None:
        if self.lobby_client is not None:
            self.lobby_client.close()
        self.lobby_client = None
        self.network_role = None
        self.awaiting_network = False
        self.lobbies = []
        self.lobby_code = ""

    def _send(self, message: dict[str, Any]) -> None:
        if self.lobby_client is None:
            raise ConnectionError("Keine Verbindung zum Lobby-Server.")
        self.lobby_client.send(message)

    def _relay(self, payload: dict[str, Any]) -> None:
        self._send({"type": "relay", "payload": payload})

    def poll(self) -> list[str]:
        """Verarbeitet Netzwerkereignisse und meldet UI-relevante Änderungen."""

        changes: list[str] = []
        endpoint = self.lobby_client
        if endpoint is None:
            return changes
        while True:
            try:
                event = endpoint.events.get_nowait()
            except queue.Empty:
                break
            event_type = event.get("event")
            if event_type == "connected":
                if self.network_role == "lobby_browser":
                    self._send({"type": "register", "nickname": self.nickname})
                continue
            if event_type == "connect_failed":
                self.status = (
                    f"Der Lobby-Server {DEFAULT_LOBBY_HOST}:{DEFAULT_LOBBY_PORT} "
                    f"ist nicht erreichbar. {event.get('message', '')}"
                )
                changes.append("connection_failed")
                continue
            if event_type in {"disconnected", "error"}:
                self.status = str(
                    event.get("message", "Die Netzwerkverbindung wurde beendet.")
                )
                changes.append("disconnected")
                continue
            if event_type != "message":
                continue
            message = event.get("message", {})
            if not isinstance(message, dict):
                continue
            message_type = message.get("type")
            if message_type == "registered":
                self.status = "Mit dem Lobby-Server verbunden."
                changes.append("lobby_ready")
            elif message_type == "lobby_list":
                self.lobbies = [
                    item for item in message.get("lobbies", []) if isinstance(item, dict)
                ]
                changes.append("lobbies")
            elif message_type == "lobby_created":
                self.network_role = "lobby_host"
                self.local_player_id = 0
                self.lobby_code = str(message.get("code", ""))
                self.status = "Warte auf einen Mitspieler …"
                changes.append("waiting")
            elif message_type == "lobby_joined":
                self.network_role = "lobby_client"
                self.local_player_id = 1
                self.lobby_code = str(message.get("code", ""))
                self.status = "Der Host bereitet die Partie vor …"
                changes.append("waiting")
            elif message_type == "peer_joined" and self.is_host:
                self._start_online_game(str(message.get("nickname", "Gast")))
                changes.append("game")
            elif message_type == "peer_left":
                self.status = str(message.get("message", "Der Mitspieler hat die Lobby verlassen."))
                changes.append("peer_left")
            elif message_type == "server_error":
                self.awaiting_network = False
                self.status = str(message.get("message", "Anfrage wurde abgelehnt."))
                changes.append("error")
            elif message_type == "relay":
                payload = message.get("payload", {})
                if isinstance(payload, dict):
                    changes.extend(self._handle_relay(payload))
        return changes

    def _start_online_game(self, remote_nickname: str) -> None:
        remote_nickname = self.clean_nickname(remote_nickname) or "Gast"
        self.game = KnackGame(2, starting_coins=self.starting_coins)
        self.game.players[0].name = self.nickname
        self.game.players[1].name = remote_nickname
        self.game.players[0].is_human = True
        self.game.players[1].is_human = True
        self.status = f"{remote_nickname} ist verbunden."
        self._send_host_state()

    def _handle_relay(self, message: dict[str, Any]) -> list[str]:
        if self.is_host:
            self._handle_remote_action(message)
            return ["game"]
        if self.is_client and message.get("type") == "state":
            self.game = game_from_snapshot(message)
            self.local_player_id = int(message["viewer_id"])
            self.awaiting_network = False
            self.status = ""
            return ["game"]
        if self.is_client and message.get("type") == "error":
            self.awaiting_network = False
            self.status = str(message.get("message", "Aktion abgelehnt."))
            return ["error"]
        return []

    def _handle_remote_action(self, message: dict[str, Any]) -> None:
        if self.game is None:
            return
        try:
            if message.get("type") != "action":
                raise IllegalMove("Unbekannte Netzwerknachricht.")
            self._apply_to_game(1, str(message.get("action", "")), message)
        except (IllegalMove, TypeError, ValueError) as exc:
            self._relay({"type": "error", "message": str(exc)})
            return
        self.status = ""
        self._send_host_state()

    def _send_host_state(self) -> None:
        if self.is_host and self.game is not None:
            self._relay(game_snapshot(self.game, 1))

    def can_act(self) -> bool:
        return bool(
            self.game
            and not self.game.round_over
            and self.game.current_player_id == self.local_player_id
            and self.game.players[self.local_player_id].active
            and not self.awaiting_network
        )

    def action(
        self,
        action: str,
        *,
        hand_index: Optional[int] = None,
        center_index: Optional[int] = None,
    ) -> None:
        if self.game is None:
            raise IllegalMove("Es läuft keine Partie.")
        extra: dict[str, int] = {}
        if action == "swap_one":
            if hand_index is None or center_index is None:
                raise IllegalMove("Bitte eine Hand- und eine Mittelkarte auswählen.")
            extra = {"hand_index": hand_index, "center_index": center_index}
        if self.is_client:
            self._relay({"type": "action", "action": action, **extra})
            self.awaiting_network = True
            self.status = "Zug wird vom Host bestätigt …"
            return
        self._apply_to_game(self.local_player_id, action, extra)
        self.status = ""
        self._send_host_state()

    def _apply_to_game(self, player_id: int, action: str, data: dict[str, Any]) -> None:
        assert self.game is not None
        if action == "pass":
            self.game.pass_turn(player_id)
        elif action == "swap_one":
            self.game.swap_one(
                player_id, int(data.get("hand_index", -1)), int(data.get("center_index", -1))
            )
        elif action == "swap_all":
            self.game.swap_all(player_id)
        elif action == "close":
            self.game.close(player_id)
        elif action == "knack":
            self.game.knack(player_id)
        elif action == "jackpot":
            self.game.jackpot(player_id)
        else:
            raise IllegalMove("Unbekannte Aktion.")

    def next_round(self) -> None:
        if self.game is None:
            return
        if self.is_client:
            raise IllegalMove("Nur der Host kann die nächste Runde starten.")
        self.game.start_round()
        self.status = ""
        self._send_host_state()

    def run_ai_turn(self) -> bool:
        """Führt genau einen Computerzug aus; die UI bestimmt das Tempo."""

        if self.game is None or self.online or self.game.round_over:
            return False
        player = self.game.current_player
        if player is None or player.is_human:
            return False
        if self.game.can_jackpot(player.id):
            self.game.jackpot(player.id)
        elif self.game.can_knack(player.id):
            self.game.knack(player.id)
        else:
            score = evaluate_hand(player.hand)
            can_close = "close" in self.game.available_actions(player.id)
            joining_close = self.game.closing_remaining is not None
            very_strong = score.kind == "halbe" or (
                score.kind == "normal" and score.value >= 29
            )
            if joining_close and can_close and very_strong and self.game.rng.random() < 0.55:
                self.game.close(player.id)
            elif not joining_close and can_close and very_strong and self.game.rng.random() < 0.72:
                self.game.close(player.id)
            else:
                action, hand_index, center_index, _ = best_exchange(
                    player.hand, self.game.center
                )
                if action == "swap_one":
                    self.game.swap_one(player.id, hand_index, center_index)  # type: ignore[arg-type]
                elif action == "swap_all":
                    self.game.swap_all(player.id)
                elif (
                    can_close
                    and score.kind == "normal"
                    and score.value >= 25
                    and self.game.rng.random() < 0.32
                ):
                    self.game.close(player.id)
                else:
                    self.game.pass_turn(player.id)
        return True

