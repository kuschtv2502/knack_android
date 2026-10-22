"""Knack für Android – Kivy-Oberfläche mit Crossplay zur PC-Version."""

from __future__ import annotations

__version__ = "17.0.1"

import os
from pathlib import Path
from typing import Optional

os.environ.setdefault("KIVY_NO_ARGS", "1")

from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.core.window import Window
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import FadeTransition, Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from knack.engine import IllegalMove, evaluate_hand
from knack.mobile_controller import MobileController


GOLD = (0.96, 0.69, 0.24, 1)
GOLD_DARK = (0.48, 0.33, 0.10, 1)
GREEN = (0.012, 0.19, 0.16, 0.96)
GREEN_LIGHT = (0.035, 0.29, 0.23, 0.96)
GREEN_DARK = (0.002, 0.10, 0.09, 0.96)
CREAM = (0.96, 0.94, 0.83, 1)
MUTED = (0.70, 0.76, 0.70, 1)
RED = (0.88, 0.25, 0.25, 1)

ROOT = Path(__file__).resolve().parent


def asset(*parts: str) -> str:
    return str(ROOT.joinpath("assets", *parts))


def card_asset(card, size: str = "large") -> str:
    rank = {
        "Ass": "ass",
        "Bube": "bube",
        "Dame": "dame",
        "König": "koenig",
    }.get(card.rank, card.rank)
    suit = {"Karo": "karo", "Herz": "herz", "Pik": "pik", "Kreuz": "kreuz"}[card.suit]
    return asset("cards", size, f"{rank}_{suit}.png")


class Panel(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*GREEN)
            self.panel_bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(16)])
        with self.canvas.after:
            Color(*GOLD_DARK)
            self.panel_border = Line(rounded_rectangle=(*self.pos, *self.size, dp(16)), width=1.2)
        self.bind(pos=self._sync_canvas, size=self._sync_canvas)

    def _sync_canvas(self, *_args):
        self.panel_bg.pos = self.pos
        self.panel_bg.size = self.size
        self.panel_border.rounded_rectangle = (*self.pos, *self.size, dp(16))


class GoldButton(Button):
    def __init__(self, primary: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.primary = primary
        self.background_normal = ""
        self.background_down = ""
        self.background_disabled_normal = ""
        self.background_color = GOLD if primary else GREEN_LIGHT
        self.color = GREEN_DARK if primary else CREAM
        self.disabled_color = (0.45, 0.49, 0.46, 1)
        self.font_size = sp(15)
        self.bold = True


class CardButton(ButtonBehavior, Image):
    zone = StringProperty("")
    card_index = NumericProperty(-1)
    selected = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.fit_mode = "contain"
        with self.canvas.after:
            self.border_color = Color(*GOLD)
            self.border = Line(rectangle=(*self.pos, *self.size), width=2)
        self.bind(pos=self._sync_border, size=self._sync_border, selected=self._sync_selected)
        self._sync_selected()

    def _sync_border(self, *_args):
        self.border.rectangle = (*self.pos, *self.size)

    def _sync_selected(self, *_args):
        self.border_color.a = 1 if self.selected else 0


class BaseScreen(Screen):
    def background(self) -> BoxLayout:
        root = FloatLayout()
        root.add_widget(
            Image(
                source=asset("background", "table.png"),
                fit_mode="cover",
                allow_stretch=True,
                keep_ratio=False,
            )
        )
        shade = Widget()
        with shade.canvas:
            Color(0, 0.04, 0.035, 0.48)
            shade.rect = RoundedRectangle(pos=shade.pos, size=shade.size)
        shade.bind(pos=lambda w, _v: setattr(w.rect, "pos", w.pos))
        shade.bind(size=lambda w, _v: setattr(w.rect, "size", w.size))
        root.add_widget(shade)
        content = BoxLayout(orientation="vertical", padding=dp(18), spacing=dp(10))
        root.add_widget(content)
        self.add_widget(root)
        return content


def title_label(text: str, size: int = 34) -> Label:
    return Label(text=text, color=GOLD, font_size=sp(size), bold=True, size_hint_y=None, height=dp(size + 18))


def field(text: str = "", *, numeric: bool = False) -> TextInput:
    return TextInput(
        text=text,
        multiline=False,
        input_filter="int" if numeric else None,
        foreground_color=CREAM,
        cursor_color=GOLD,
        background_normal="",
        background_active="",
        background_color=(0.015, 0.17, 0.15, 1),
        padding=(dp(12), dp(10)),
        font_size=sp(16),
        size_hint_y=None,
        height=dp(46),
    )


class StartScreen(BaseScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        outer = self.background()
        outer.add_widget(Widget(size_hint_y=0.05))
        panel = Panel(
            orientation="vertical",
            spacing=dp(9),
            padding=(dp(42), dp(22)),
            size_hint=(0.72, 0.90),
            pos_hint={"center_x": 0.5},
        )
        outer.add_widget(panel)
        panel.add_widget(title_label("KNACK", 48))
        panel.add_widget(
            Label(
                text="Das Kartenspiel nach euren Hausregeln",
                color=CREAM,
                bold=True,
                font_size=sp(20),
                size_hint_y=None,
                height=dp(34),
            )
        )
        panel.add_widget(
            Label(
                text="Spiele lokal gegen Computer oder per Crossplay mit Windows-Spielern.",
                color=MUTED,
                font_size=sp(14),
                size_hint_y=None,
                height=dp(30),
            )
        )
        form = GridLayout(cols=4, spacing=dp(10), size_hint_y=None, height=dp(110))
        form.add_widget(Label(text="Nickname", color=CREAM, bold=True))
        self.nickname = field("Spieler")
        form.add_widget(self.nickname)
        form.add_widget(Label(text="Spielerzahl", color=CREAM, bold=True))
        self.players = field("3", numeric=True)
        form.add_widget(self.players)
        form.add_widget(Label(text="Startmünzen", color=CREAM, bold=True))
        self.coins = field("3", numeric=True)
        form.add_widget(self.coins)
        form.add_widget(Widget())
        form.add_widget(Widget())
        panel.add_widget(form)
        local_button = GoldButton(text="▶  Lokales Spiel starten", primary=True, size_hint_y=None, height=dp(54))
        local_button.bind(on_release=lambda *_: self.start_local())
        panel.add_widget(local_button)
        online_button = GoldButton(text="♟  Online-Lobby-Browser öffnen", size_hint_y=None, height=dp(52))
        online_button.bind(on_release=lambda *_: self.open_online())
        panel.add_widget(online_button)
        self.message = Label(text="", color=RED, font_size=sp(13), size_hint_y=None, height=dp(26))
        panel.add_widget(self.message)

    def values(self) -> tuple[str, int, int]:
        nickname = self.nickname.text.strip()
        players = int(self.players.text or "0")
        coins = int(self.coins.text or "0")
        if not 2 <= players <= 9:
            raise ValueError("Die Spielerzahl muss zwischen 2 und 9 liegen.")
        if not 1 <= coins <= 99:
            raise ValueError("Die Startmünzen müssen zwischen 1 und 99 liegen.")
        return nickname, players, coins

    def start_local(self) -> None:
        try:
            nickname, players, coins = self.values()
            App.get_running_app().start_local(nickname, players, coins)
            self.message.text = ""
        except (ValueError, IllegalMove) as exc:
            self.message.text = str(exc)

    def open_online(self) -> None:
        try:
            nickname, _players, coins = self.values()
            App.get_running_app().open_online(nickname, coins)
            self.message.text = ""
        except (ValueError, ConnectionError) as exc:
            self.message.text = str(exc)


class LobbyScreen(BaseScreen):
    selected_code = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        outer = self.background()
        header = BoxLayout(size_hint_y=None, height=dp(62), spacing=dp(12))
        header.add_widget(title_label("ONLINE-LOBBYS", 30))
        self.server_label = Label(text="kuschtv.zapto.org:45455", color=CREAM, halign="right")
        header.add_widget(self.server_label)
        outer.add_widget(header)
        panel = Panel(orientation="vertical", padding=dp(16), spacing=dp(9))
        outer.add_widget(panel)
        panel.add_widget(
            Label(
                text="Verfügbare Partien",
                color=GOLD,
                bold=True,
                font_size=sp(22),
                size_hint_y=None,
                height=dp(38),
                halign="left",
            )
        )
        scroll = ScrollView(do_scroll_x=False)
        self.rows = GridLayout(cols=1, spacing=dp(6), size_hint_y=None)
        self.rows.bind(minimum_height=self.rows.setter("height"))
        scroll.add_widget(self.rows)
        panel.add_widget(scroll)
        self.status = Label(text="Verbinde …", color=MUTED, size_hint_y=None, height=dp(28))
        panel.add_widget(self.status)
        controls = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        self.lobby_name = field("Spielers Runde")
        self.lobby_name.size_hint_x = 1.3
        controls.add_widget(self.lobby_name)
        create = GoldButton(text="+ Lobby erstellen", primary=True)
        create.bind(on_release=lambda *_: self.create_lobby())
        controls.add_widget(create)
        join = GoldButton(text="Beitreten")
        join.bind(on_release=lambda *_: self.join_selected())
        controls.add_widget(join)
        refresh = GoldButton(text="Aktualisieren")
        refresh.bind(on_release=lambda *_: self.refresh_lobbies())
        controls.add_widget(refresh)
        back = GoldButton(text="Zurück")
        back.bind(on_release=lambda *_: App.get_running_app().to_menu())
        controls.add_widget(back)
        panel.add_widget(controls)

    def update_rows(self) -> None:
        controller = App.get_running_app().controller
        self.rows.clear_widgets()
        if not controller.lobbies:
            self.rows.add_widget(
                Label(
                    text="Zurzeit ist keine Lobby geöffnet. Erstelle einfach die erste.",
                    color=MUTED,
                    size_hint_y=None,
                    height=dp(55),
                )
            )
        for lobby in controller.lobbies:
            code = str(lobby.get("code", ""))
            joinable = bool(lobby.get("joinable"))
            status = "FREI" if joinable else "IM SPIEL"
            text = (
                f"{lobby.get('name', 'Knack-Runde')}    •    Host: {lobby.get('host', 'Spieler')}"
                f"    •    {lobby.get('players', 1)}/{lobby.get('capacity', 2)}    •    {status}"
            )
            row = GoldButton(text=text, size_hint_y=None, height=dp(50))
            row.disabled = not joinable
            row.bind(on_release=lambda _button, value=code: self.select(value))
            self.rows.add_widget(row)
        self.status.text = controller.status

    def select(self, code: str) -> None:
        self.selected_code = code
        self.status.text = f"Lobby {code} ausgewählt."

    def create_lobby(self) -> None:
        try:
            App.get_running_app().controller.create_lobby(self.lobby_name.text)
        except (ValueError, ConnectionError) as exc:
            self.status.text = str(exc)

    def join_selected(self) -> None:
        try:
            App.get_running_app().controller.join_lobby(self.selected_code)
        except (ValueError, ConnectionError) as exc:
            self.status.text = str(exc)

    def refresh_lobbies(self) -> None:
        try:
            App.get_running_app().controller.refresh_lobbies()
        except ConnectionError as exc:
            self.status.text = str(exc)


class WaitingScreen(BaseScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        outer = self.background()
        outer.add_widget(Widget(size_hint_y=0.15))
        panel = Panel(
            orientation="vertical",
            padding=dp(35),
            spacing=dp(14),
            size_hint=(0.64, 0.65),
            pos_hint={"center_x": 0.5},
        )
        outer.add_widget(panel)
        panel.add_widget(title_label("LOBBY IST GEÖFFNET", 30))
        self.detail = Label(text="", color=CREAM, font_size=sp(18), halign="center")
        panel.add_widget(self.detail)
        cancel = GoldButton(text="Abbrechen", size_hint_y=None, height=dp(50))
        cancel.bind(on_release=lambda *_: App.get_running_app().to_menu())
        panel.add_widget(cancel)

    def update_detail(self) -> None:
        controller = App.get_running_app().controller
        self.detail.text = (
            f"Lobbycode: {controller.lobby_code}\n\n{controller.status}\n\n"
            "Die Lobby ist auch für Spieler der Windows-Version sichtbar."
        )


class GameScreen(BaseScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        outer = self.background()
        header = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))
        self.round_label = Label(text="KNACK", color=GOLD, bold=True, font_size=sp(26), halign="left")
        self.pot_label = Label(text="Pot: 0", color=CREAM, bold=True, font_size=sp(17), halign="right")
        header.add_widget(self.round_label)
        header.add_widget(self.pot_label)
        menu = GoldButton(text="Menü", size_hint_x=None, width=dp(90))
        menu.bind(on_release=lambda *_: App.get_running_app().to_menu())
        header.add_widget(menu)
        outer.add_widget(header)

        body = BoxLayout(spacing=dp(10))
        outer.add_widget(body)
        table = Panel(orientation="vertical", padding=dp(9), spacing=dp(5), size_hint_x=0.79)
        sidebar = Panel(orientation="vertical", padding=dp(10), spacing=dp(5), size_hint_x=0.21)
        body.add_widget(table)
        body.add_widget(sidebar)

        opponent_scroll = ScrollView(size_hint_y=0.22, do_scroll_y=False)
        self.opponents = GridLayout(rows=1, spacing=dp(8), size_hint_x=None)
        self.opponents.bind(minimum_width=self.opponents.setter("width"))
        opponent_scroll.add_widget(self.opponents)
        table.add_widget(opponent_scroll)

        self.center_title = Label(text="MITTE", color=GOLD, bold=True, size_hint_y=None, height=dp(22))
        table.add_widget(self.center_title)
        center_line = BoxLayout(size_hint_y=0.27, spacing=dp(8), padding=(dp(5), 0))
        center_line.add_widget(Widget())
        self.center_cards = BoxLayout(spacing=dp(7), size_hint_x=None, width=dp(320))
        center_line.add_widget(self.center_cards)
        self.cemetery = BoxLayout(orientation="vertical", size_hint_x=None, width=dp(76))
        center_line.add_widget(self.cemetery)
        center_line.add_widget(Widget())
        table.add_widget(center_line)

        self.hand_title = Label(text="DEINE HAND", color=GOLD, bold=True, size_hint_y=None, height=dp(24))
        table.add_widget(self.hand_title)
        hand_line = BoxLayout(size_hint_y=0.29)
        hand_line.add_widget(Widget())
        self.hand_cards = BoxLayout(spacing=dp(7), size_hint_x=None, width=dp(320))
        hand_line.add_widget(self.hand_cards)
        hand_line.add_widget(Widget())
        table.add_widget(hand_line)

        self.score = Label(text="", color=CREAM, bold=True, size_hint_y=None, height=dp(25))
        table.add_widget(self.score)
        self.actions = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(5))
        self.action_buttons: dict[str, GoldButton] = {}
        for action, caption in (
            ("pass", "Schieben"),
            ("swap_one", "1 Karte"),
            ("swap_all", "Alle 3"),
            ("close", "Zumachen"),
            ("knack", "KNACK!"),
            ("jackpot", "JACKPOT!"),
        ):
            button = GoldButton(text=caption, primary=action == "pass")
            button.bind(on_release=lambda _button, value=action: self.perform(value))
            self.action_buttons[action] = button
            self.actions.add_widget(button)
        table.add_widget(self.actions)
        self.message = Label(text="", color=MUTED, font_size=sp(12), size_hint_y=None, height=dp(25))
        table.add_widget(self.message)

        sidebar.add_widget(Label(text="RUNDENPROTOKOLL", color=GOLD, bold=True, font_size=sp(18), size_hint_y=None, height=dp(35)))
        log_scroll = ScrollView()
        self.log_label = Label(text="", color=CREAM, font_size=sp(12), halign="left", valign="top", size_hint_y=None)
        self.log_label.bind(texture_size=lambda w, value: setattr(w, "height", value[1] + dp(10)))
        self.log_label.bind(width=lambda w, value: setattr(w, "text_size", (value, None)))
        log_scroll.add_widget(self.log_label)
        sidebar.add_widget(log_scroll)
        self.result_label = Label(text="", color=GOLD, bold=True, halign="center", size_hint_y=None, height=dp(62))
        sidebar.add_widget(self.result_label)
        self.next_button = GoldButton(text="Nächste Runde", primary=True, size_hint_y=None, height=dp(48))
        self.next_button.bind(on_release=lambda *_: self.next_round())
        sidebar.add_widget(self.next_button)

        self.selected_hand: Optional[int] = None
        self.selected_center: Optional[int] = None

    def select_card(self, zone: str, index: int) -> None:
        if not App.get_running_app().controller.can_act():
            return
        if zone == "hand":
            self.selected_hand = None if self.selected_hand == index else index
        else:
            self.selected_center = None if self.selected_center == index else index
        App.get_running_app().play_sound("card")
        self.update_game()

    def _card_button(self, source: str, zone: str, index: int, selected: bool) -> CardButton:
        button = CardButton(
            source=source,
            zone=zone,
            card_index=index,
            selected=selected,
            size_hint=(None, 1),
            width=dp(98),
        )
        button.bind(on_release=lambda widget: self.select_card(widget.zone, int(widget.card_index)))
        return button

    def update_game(self) -> None:
        app = App.get_running_app()
        controller = app.controller
        game = controller.game
        if game is None:
            return
        self.round_label.text = f"KNACK  ·  Runde {game.round_number}"
        self.pot_label.text = f"Pot: ◉ {game.pot}"
        active = game.current_player
        turn_text = "Runde beendet" if active is None else f"{active.name} ist am Zug"
        self.hand_title.text = f"DEINE HAND  ·  ◉ {game.players[controller.local_player_id].coins}  ·  {turn_text.upper()}"

        self.opponents.clear_widgets()
        for player in game.players:
            if player.id == controller.local_player_id:
                continue
            is_winner = bool(game.result and player.id in game.result.winner_ids)
            is_closer = player.id in game.closing_player_ids
            color = GOLD if is_winner else (RED if is_closer else CREAM)
            box = Panel(
                orientation="vertical",
                padding=dp(5),
                spacing=dp(2),
                size_hint_x=None,
                width=dp(255),
            )
            caption = ("★ RUNDENSIEGER  " if is_winner else "") + f"{player.name}  ·  ◉ {player.coins}"
            box.add_widget(Label(text=caption, color=color, bold=True, size_hint_y=None, height=dp(25)))
            cards = BoxLayout(spacing=dp(4))
            visible_cards = player.hand
            hidden_card_count = int(getattr(player, "hand_count", len(visible_cards)))
            for index in range(hidden_card_count if not visible_cards else len(visible_cards)):
                source = card_asset(visible_cards[index], "medium") if visible_cards else asset("cards", "medium", "back.png")
                cards.add_widget(Image(source=source, fit_mode="contain"))
            box.add_widget(cards)
            self.opponents.add_widget(box)

        self.center_cards.clear_widgets()
        for index, card in enumerate(game.center):
            self.center_cards.add_widget(
                self._card_button(card_asset(card), "center", index, self.selected_center == index)
            )

        self.hand_cards.clear_widgets()
        own = game.players[controller.local_player_id]
        for index, card in enumerate(own.hand):
            self.hand_cards.add_widget(
                self._card_button(card_asset(card), "hand", index, self.selected_hand == index)
            )

        self.cemetery.clear_widgets()
        self.cemetery.add_widget(Label(text=f"FRIEDHOF · {len(game.discard)}", color=CREAM, font_size=sp(10), size_hint_y=None, height=dp(20)))
        if game.discard:
            self.cemetery.add_widget(Image(source=card_asset(game.discard[-1], "small"), fit_mode="contain"))
        else:
            self.cemetery.add_widget(Label(text="leer", color=MUTED))

        self.score.text = f"Aktuelle Wertung: {evaluate_hand(own.hand).label}" if len(own.hand) == 3 else ""
        allowed = game.available_actions(controller.local_player_id) if controller.can_act() else set()
        for action, button in self.action_buttons.items():
            button.disabled = action not in allowed
        if "close" in allowed and game.closing_remaining is not None:
            self.action_buttons["close"].text = "Mit zumachen"
        else:
            self.action_buttons["close"].text = "Zumachen"
        self.message.text = controller.status or (
            "Für den Einzeltausch je eine Hand- und Mittelkarte auswählen."
        )
        self.log_label.text = "\n".join(game.log)

        self.next_button.opacity = 1 if game.round_over and not controller.is_client and not game.game_over else 0
        self.next_button.disabled = not (game.round_over and not controller.is_client and not game.game_over)
        if game.round_over and game.result:
            winners = ", ".join(game.players[index].name for index in game.result.winner_ids)
            self.result_label.text = f"Runde beendet · {game.result.reason}\nRundensieger: {winners}"
        elif game.game_over:
            winner = game.players[game.game_winner_id].name if game.game_winner_id is not None else "Remis"
            self.result_label.text = f"PARTIE BEENDET\n{winner}"
        else:
            self.result_label.text = ""

        if active and active.id == controller.local_player_id and not game.round_over:
            Animation.cancel_all(self.hand_title)
            self.hand_title.opacity = 0.45
            Animation(opacity=1, duration=0.35).start(self.hand_title)

    def perform(self, action: str) -> None:
        app = App.get_running_app()
        try:
            app.controller.action(
                action,
                hand_index=self.selected_hand,
                center_index=self.selected_center,
            )
        except (IllegalMove, ConnectionError, ValueError) as exc:
            app.controller.status = str(exc)
        else:
            self.selected_hand = None
            self.selected_center = None
            app.play_sound("knack" if action == "knack" else "jackpot" if action == "jackpot" else "card")
        self.update_game()
        app.schedule_ai()

    def next_round(self) -> None:
        app = App.get_running_app()
        try:
            app.controller.next_round()
        except (IllegalMove, ConnectionError) as exc:
            app.controller.status = str(exc)
        self.selected_hand = None
        self.selected_center = None
        self.update_game()
        app.schedule_ai()


class KnackAndroidApp(App):
    title = "Knack – Kartenspiel"

    def build(self):
        Window.clearcolor = GREEN_DARK
        self.controller = MobileController()
        self.sounds = {}
        self.ai_event = None
        self.manager = ScreenManager(transition=FadeTransition(duration=0.18))
        self.start_screen = StartScreen(name="start")
        self.lobby_screen = LobbyScreen(name="lobby")
        self.waiting_screen = WaitingScreen(name="waiting")
        self.game_screen = GameScreen(name="game")
        for screen in (self.start_screen, self.lobby_screen, self.waiting_screen, self.game_screen):
            self.manager.add_widget(screen)
        Clock.schedule_interval(self.poll_network, 0.08)
        return self.manager

    def start_local(self, nickname: str, players: int, coins: int) -> None:
        self.controller.start_local(nickname, players, coins)
        self.manager.current = "game"
        self.game_screen.update_game()
        self.play_sound("deal")
        self.schedule_ai()

    def open_online(self, nickname: str, coins: int) -> None:
        self.controller.connect_lobby(nickname, coins)
        self.manager.current = "lobby"
        self.lobby_screen.selected_code = ""
        self.lobby_screen.update_rows()

    def to_menu(self) -> None:
        if self.ai_event is not None:
            self.ai_event.cancel()
            self.ai_event = None
        self.controller.leave_to_menu()
        self.manager.current = "start"

    def poll_network(self, _dt: float) -> None:
        for change in self.controller.poll():
            if change in {"lobby_ready", "lobbies"}:
                if self.manager.current != "lobby":
                    self.manager.current = "lobby"
                self.lobby_screen.update_rows()
            elif change == "waiting":
                self.manager.current = "waiting"
                self.waiting_screen.update_detail()
            elif change == "game":
                was_in_game = self.manager.current == "game"
                self.manager.current = "game"
                self.game_screen.update_game()
                self.play_sound("turn" if was_in_game else "deal")
            elif change in {"connection_failed", "disconnected", "peer_left"}:
                self.show_message("Netzwerk", self.controller.status)
                self.to_menu()
            elif change == "error":
                if self.manager.current == "game":
                    self.game_screen.update_game()
                elif self.manager.current == "lobby":
                    self.lobby_screen.update_rows()

    def schedule_ai(self) -> None:
        game = self.controller.game
        if (
            game
            and not self.controller.online
            and not game.round_over
            and game.current_player is not None
            and not game.current_player.is_human
            and self.ai_event is None
        ):
            self.ai_event = Clock.schedule_once(self.run_ai, 0.65)

    def run_ai(self, _dt: float) -> None:
        self.ai_event = None
        try:
            moved = self.controller.run_ai_turn()
        except (IllegalMove, RuntimeError) as exc:
            self.show_message("Spielzug nicht möglich", str(exc))
            return
        if moved:
            self.game_screen.update_game()
            self.play_sound("card")
        self.schedule_ai()

    def play_sound(self, name: str) -> None:
        sound = self.sounds.get(name)
        if sound is None:
            sound = SoundLoader.load(asset("sounds", f"{name}.wav"))
            self.sounds[name] = sound
        if sound is not None:
            sound.stop()
            sound.play()

    @staticmethod
    def show_message(title: str, message: str) -> None:
        content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))
        content.add_widget(Label(text=message, color=CREAM, halign="center"))
        close = GoldButton(text="OK", primary=True, size_hint_y=None, height=dp(48))
        popup = Popup(title=title, content=content, size_hint=(0.65, 0.46))
        close.bind(on_release=popup.dismiss)
        content.add_widget(close)
        popup.open()

    def on_stop(self) -> None:
        self.controller.stop_network()


if __name__ == "__main__":
    KnackAndroidApp().run()

