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
   python requirements-install.py

2. Der Explorer wird sich öffnen, in dem du die Datei (`Pythonskript` oder `requirements.txt`) auswählen kannst.
   Du kannst auch mehrere Dateien auswählen. Diese werden automatisch nacheinander bearbeitet.

3. Das Skript wird nun damit beginnen, alle nötigen Bibliotheken nachzuinstallieren.

## Dateitypen

Das Skript unterstützt folgende Dateitypen:

- `Python-Skripte (.py)`: Es analysiert die Datei und extrahiert alle importierten Module.
- `requirements.txt`: Es liest die Datei und extrahiert die dort aufgelisteten Pakete.

## Fehlertoleranz

- Das Skript verwendet einen Retry-Mechanismus bei der Installation von Paketen, der die Installation nach einem Fehler bis zu dreimal wiederholt.
- Es werden Netzwerkprobleme, Berechtigungsfehler und systemweite Abhängigkeiten wie `pg_config` und `gcc` erkannt und die entsprechenden Fehlermeldungen angezeigt.

## Wichtige Funktionen

- Import-Extraktion: Das Skript verwendet das `ast`-Modul, um alle `import`- und `from ... import`-Anweisungen aus Python-Dateien zu analysieren.
- Paketerkennung: Überprüft mithilfe von `importlib` und `metadata`, ob eine Bibliothek bereits installiert ist.
- Installation: Fehlende Pakete werden automatisch installiert, falls sie nicht gefunden werden.
- Paketverwaltung: Es wird eine rudimentäre Verwaltung der Installationsversuche verwendet, um bei Fehlern eine exponentielle Verzögerung zwischen den Versuchen zu ermöglichen.

## Bekannte Einschränkungen

Das Skript erkennt nicht automatisch, ob Bibliotheken spezielle Systemabhängigkeiten benötigen (z. B. C-Compiler).
Bei sehr großen `requirements.txt`-Dateien kann die Verarbeitung länger dauern.
