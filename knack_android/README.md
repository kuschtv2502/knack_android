# Knack für Android – V17

Diese Version ist eine echte Android-App auf Basis von Kivy. Sie verwendet
dieselbe Regel-Engine und dasselbe Netzwerkprotokoll wie Knack V16 für
Windows. Dadurch sind folgende Kombinationen möglich:

- Android erstellt eine Lobby, Windows tritt bei,
- Windows erstellt eine Lobby, Android tritt bei,
- zwei Android-Geräte spielen miteinander,
- lokales Spiel auf Android gegen bis zu acht Computergegner.

Der Lobby-Server ist fest auf `kuschtv.zapto.org:45455` eingestellt. Die
Online-Partie bleibt vorerst wie in V16 auf zwei menschliche Spieler begrenzt.

## APK ohne Linux bauen

1. Den Inhalt dieses Ordners in ein eigenes GitHub-Repository hochladen.
2. Auf GitHub den Reiter **Actions** öffnen.
3. Links **Android-APK bauen** auswählen.
4. **Run workflow** und danach nochmals **Run workflow** anklicken.
5. Der erste Bau kann deutlich länger dauern, weil Android-Werkzeuge geladen
   werden. Nach erfolgreichem Abschluss den Lauf öffnen.
6. Unten unter **Artifacts** `Knack-Android-V17` herunterladen und entpacken.
7. Die enthaltene APK auf das Smartphone kopieren und öffnen. Android fragt
   beim ersten Mal, ob Installationen aus dieser Quelle erlaubt werden sollen.

Die Workflow-Datei liegt unter `.github/workflows/build-apk.yml`. Sie testet
vor jedem Bau die Spielregeln und einen vollständigen Lobby-/Crossplay-Ablauf.
Die APK unterstützt Android 8.0 und neuer und enthält sowohl ARM64 als auch
die ältere ARMv7-Architektur.

## Lokale Vorschau auf einem PC

Optional kann die Kivy-Oberfläche vor dem APK-Bau am PC getestet werden:

```text
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install kivy==2.3.1
.venv\Scripts\python main.py
```

Python 3.12 wird empfohlen, weil dafür fertige Kivy-Pakete verfügbar sind.

## Technischer Aufbau

- `main.py` – touchoptimierte Kivy-Oberfläche im Querformat
- `knack/mobile_controller.py` – gemeinsame Steuerung für lokale und Online-Spiele
- `knack/engine.py` – unveränderte Regel-Engine aus der PC-Version
- `knack/network.py` – kompatible Zustands-Snapshots
- `knack/lobby.py` – kompatibler Lobby- und Relay-Client
- `assets/` – scharfe Kartenbilder, Spieltisch und Töne
- `buildozer.spec` – Android-Paketkonfiguration
- `tests/` – lokale Logik- und Crossplay-Tests

## Wichtiger Testhinweis

Die erzeugte Debug-APK ist für private Tests und direkte Weitergabe gedacht.
Für eine Veröffentlichung im Play Store wird später ein signierter
Release-Build beziehungsweise ein AAB benötigt. Das ändert nichts am
Crossplay-Protokoll.

