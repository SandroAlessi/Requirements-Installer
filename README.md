# Python Abhängigkeitsmanager

Dieses Skript ist ein Python-Tool, das verwendet wird, um Bibliotheken automatisch aus Python-Skripten (`.py`) oder einer `requirements.txt`-Datei zu extrahieren und fehlende Pakete zu installieren.

## Funktionsweise

1. Das Skript überprüft, ob alle erforderlichen Bibliotheken, die in den ausgewählten Dateien importiert werden, auf dem System installiert sind.
2. Wenn Bibliotheken fehlen, versucht das Skript, diese mit `pip` zu installieren.
3. Es bietet eine grafische Benutzeroberfläche (GUI) mit Hilfe von `tkinter`, um Dateien auszuwählen (entweder Python-Skripte oder `requirements.txt`-Dateien).
4. Falls `pip` veraltet ist, wird eine Aktualisierung vorgeschlagen.

## Voraussetzungen

- Python 3.x
- `pip` muss installiert sein
- Für die grafische Oberfläche wird `tkinter` verwendet, das bei den meisten Python-Installationen enthalten ist.
- Bei der Installation bestimmter Bibliotheken wie `libsass` wird möglicherweise ein C-Compiler wie `gcc` benötigt.

## Installation

Stelle sicher, dass du Python und `pip` installiert hast. Falls du `tkinter` nicht installiert hast, kann das Skript es automatisch für dich installieren.

## Verwendung

1. Starte das Skript mit Python:

   ```bash
   python requirements_install.py
