"""Zentraler Lobby- und Relay-Dienst fuer Knack.

Alle Spielinstanzen bauen eine ausgehende TCP-Verbindung zu diesem Dienst auf.
Der Lobby-Ersteller bleibt fuer den Spielzustand verantwortlich; der Dienst
kennt weder Karten noch Regeln und reicht lediglich JSON-Nachrichten weiter.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import queue
import secrets
import socket
import socketserver
import threading
from typing import Any, Optional

from .network import _JsonConnection


DEFAULT_LOBBY_PORT = 45455
DEFAULT_LOBBY_HOST = "kuschtv.zapto.org"
MAX_LINE_BYTES = 1_000_000


class LobbyClient:
    """Nicht blockierender Client fuer Lobby-Browser und Relay-Verbindung."""

    def __init__(self) -> None:
        self.events: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self.connection: Optional[_JsonConnection] = None
        self.closed = False

    def connect(self, host: str, port: int = DEFAULT_LOBBY_PORT) -> None:
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
            raise ConnectionError("Keine Verbindung zum Lobby-Server.")
        self.connection.send(message)

    def close(self) -> None:
        self.closed = True
        if self.connection is not None:
            self.connection.close()
            self.connection = None


@dataclass
class _Lobby:
    code: str
    name: str
    host: "_LobbyHandler"
    guest: Optional["_LobbyHandler"] = None


class _LobbyState:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.clients: set[_LobbyHandler] = set()
        self.lobbies: dict[str, _Lobby] = {}

    @staticmethod
    def _clean_text(value: Any, limit: int, fallback: str) -> str:
        text = "".join(
            character for character in str(value).strip() if character.isprintable()
        )[:limit]
        return text or fallback

    def add(self, client: "_LobbyHandler") -> None:
        with self.lock:
            self.clients.add(client)

    def remove(self, client: "_LobbyHandler") -> None:
        with self.lock:
            self.clients.discard(client)
            self._leave_lobby(client, disconnected=True)

    def handle(self, client: "_LobbyHandler", message: Any) -> None:
        if not isinstance(message, dict):
            client.send_json({"type": "server_error", "message": "Ungueltige Nachricht."})
            return
        message_type = message.get("type")
        with self.lock:
            if message_type == "register":
                client.nickname = self._clean_text(
                    message.get("nickname", "Spieler"), 20, "Spieler"
                )
                client.send_json({"type": "registered", "nickname": client.nickname})
                self._send_lobby_list(client)
            elif message_type == "list_lobbies":
                self._send_lobby_list(client)
            elif message_type == "create_lobby":
                self._create_lobby(client, message)
            elif message_type == "join_lobby":
                self._join_lobby(client, message)
            elif message_type == "leave_lobby":
                self._leave_lobby(client)
                self._send_lobby_list(client)
            elif message_type == "relay":
                self._relay(client, message.get("payload"))
            elif message_type == "ping":
                client.send_json({"type": "pong"})
            else:
                client.send_json(
                    {"type": "server_error", "message": "Unbekannte Serveranfrage."}
                )

    def _new_code(self) -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        while True:
            code = "".join(secrets.choice(alphabet) for _ in range(6))
            if code not in self.lobbies:
                return code

    def _create_lobby(self, client: "_LobbyHandler", message: dict[str, Any]) -> None:
        if client.lobby_code is not None:
            client.send_json(
                {"type": "server_error", "message": "Du bist bereits in einer Lobby."}
            )
            return
        name = self._clean_text(message.get("name", "Knack-Runde"), 30, "Knack-Runde")
        code = self._new_code()
        self.lobbies[code] = _Lobby(code=code, name=name, host=client)
        client.lobby_code = code
        client.send_json({"type": "lobby_created", "code": code, "name": name})
        self._broadcast_lobby_list()

    def _join_lobby(self, client: "_LobbyHandler", message: dict[str, Any]) -> None:
        if client.lobby_code is not None:
            client.send_json(
                {"type": "server_error", "message": "Du bist bereits in einer Lobby."}
            )
            return
        code = str(message.get("code", "")).strip().upper()
        lobby = self.lobbies.get(code)
        if lobby is None:
            client.send_json(
                {"type": "server_error", "message": "Diese Lobby existiert nicht mehr."}
            )
            self._send_lobby_list(client)
            return
        if lobby.guest is not None:
            client.send_json(
                {"type": "server_error", "message": "Diese Lobby ist bereits voll."}
            )
            self._send_lobby_list(client)
            return
        if lobby.host is client:
            client.send_json(
                {"type": "server_error", "message": "Du hast diese Lobby erstellt."}
            )
            return
        lobby.guest = client
        client.lobby_code = code
        client.send_json(
            {
                "type": "lobby_joined",
                "code": code,
                "name": lobby.name,
                "host_nickname": lobby.host.nickname,
            }
        )
        lobby.host.send_json(
            {
                "type": "peer_joined",
                "code": code,
                "nickname": client.nickname,
            }
        )
        self._broadcast_lobby_list()

    def _leave_lobby(self, client: "_LobbyHandler", disconnected: bool = False) -> None:
        code = client.lobby_code
        if code is None:
            return
        lobby = self.lobbies.get(code)
        client.lobby_code = None
        if lobby is None:
            return
        if lobby.host is client:
            self.lobbies.pop(code, None)
            if lobby.guest is not None:
                lobby.guest.lobby_code = None
                lobby.guest.send_json(
                    {"type": "peer_left", "message": "Der Lobby-Host hat die Lobby geschlossen."}
                )
        elif lobby.guest is client:
            lobby.guest = None
            lobby.host.send_json(
                {"type": "peer_left", "message": "Der Mitspieler hat die Lobby verlassen."}
            )
        if not disconnected:
            client.send_json({"type": "lobby_left"})
        self._broadcast_lobby_list()

    def _relay(self, client: "_LobbyHandler", payload: Any) -> None:
        if not isinstance(payload, dict):
            client.send_json(
                {"type": "server_error", "message": "Ungueltige Spielnachricht."}
            )
            return
        lobby = self.lobbies.get(client.lobby_code or "")
        if lobby is None:
            client.send_json(
                {"type": "server_error", "message": "Du bist in keiner Lobby."}
            )
            return
        target = lobby.guest if lobby.host is client else lobby.host
        if target is None:
            client.send_json(
                {"type": "server_error", "message": "Noch kein Mitspieler verbunden."}
            )
            return
        target.send_json({"type": "relay", "payload": payload})

    def _lobby_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "code": lobby.code,
                "name": lobby.name,
                "host": lobby.host.nickname,
                "players": 1 if lobby.guest is None else 2,
                "capacity": 2,
                "joinable": lobby.guest is None,
            }
            for lobby in sorted(self.lobbies.values(), key=lambda item: item.name.casefold())
        ]

    def _send_lobby_list(self, client: "_LobbyHandler") -> None:
        client.send_json({"type": "lobby_list", "lobbies": self._lobby_rows()})

    def _broadcast_lobby_list(self) -> None:
        message = {"type": "lobby_list", "lobbies": self._lobby_rows()}
        for client in tuple(self.clients):
            if client.lobby_code is None:
                client.send_json(message)


class _LobbyHandler(socketserver.StreamRequestHandler):
    nickname = "Spieler"
    lobby_code: Optional[str] = None

    def setup(self) -> None:
        super().setup()
        self.nickname = "Spieler"
        self.lobby_code = None
        self._send_lock = threading.Lock()

    @property
    def state(self) -> _LobbyState:
        return self.server.state  # type: ignore[attr-defined,no-any-return]

    def send_json(self, message: dict[str, Any]) -> None:
        payload = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            with self._send_lock:
                self.request.sendall(payload)
        except OSError:
            pass

    def handle(self) -> None:
        self.state.add(self)
        try:
            for line in self.rfile:
                if len(line) > MAX_LINE_BYTES:
                    self.send_json(
                        {"type": "server_error", "message": "Nachricht ist zu gross."}
                    )
                    break
                try:
                    message = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self.send_json(
                        {"type": "server_error", "message": "Ungueltige JSON-Nachricht."}
                    )
                    continue
                self.state.handle(self, message)
        except (ConnectionError, OSError):
            pass
        finally:
            self.state.remove(self)


class _ThreadingLobbyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], state: _LobbyState) -> None:
        self.state = state
        super().__init__(address, _LobbyHandler)


class LobbyServer:
    """Einbettbarer Server, der auch in Netzwerktests gestartet werden kann."""

    def __init__(self, host: str = "0.0.0.0", port: int = DEFAULT_LOBBY_PORT) -> None:
        self.host = host
        self.port = port
        self.state = _LobbyState()
        self.server: Optional[_ThreadingLobbyServer] = None
        self.thread: Optional[threading.Thread] = None

    def start(self, *, background: bool = True) -> None:
        self.server = _ThreadingLobbyServer((self.host, self.port), self.state)
        self.port = int(self.server.server_address[1])
        if background:
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
        else:
            self.server.serve_forever()

    def close(self) -> None:
        if self.server is None:
            return
        self.server.shutdown()
        self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=2)
        self.server = None
        self.thread = None

