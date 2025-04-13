# Requirements-Installer (v2.0.0)

![Python](https://img.shields.io/badge/Python-3.7%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/OS-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
![GUI](https://img.shields.io/badge/GUI-optional-informational)
![CLI](https://img.shields.io/badge/Modus-CLI%20%7C%20GUI-blueviolet)
![Status](https://img.shields.io/badge/status-produktiv-brightgreen)

Ein flexibles Werkzeug zur automatisierten Installation von Python-Abhängigkeiten aus `.py`- und `requirements.txt`-Dateien – interaktiv, rekursiv, fehlertolerant und vollständig konfigurierbar.

---

## Inhaltsverzeichnis

- [Merkmale](#merkmale)
- [Voraussetzungen](#voraussetzungen)
- [Installation](#installation)
- [Verwendung](#verwendung)
- [Hinweis zur Paket-Erkennung (Mapping)](#hinweis-zur-paket-erkennung-mapping)
- [Windows-Kontextmenü (optional)](#windows-kontextmenü-optional)
- [Konfiguration](#konfiguration)
- [Bekannte Einschränkungen](#bekannte-einschränkungen)
- [Lizenz](#lizenz)

---

## Merkmale

- 🔍 AST-Analyse von `.py`-Dateien zur Import-Erkennung
- 📦 Automatische Installation fehlender Pakete via `pip`
- 📂 Rekursive Verzeichnissuche mit Unterstützung für mehrere Pfade
- 🎛️ Benutzerdefinierbares Mapping Import → Paketname (`mapping.json`)
- 🖱️ GUI-Dateiauswahl über `tkinter` (optional)
- 💬 Farbiges Logging mit optionalem `colorama`
- 🔁 Wiederholungsversuche mit exponentiellem Backoff bei Installationsfehlern
- 🧪 Heuristiken für Compiler-/System-Abhängigkeiten (`gcc`, `pg_config`)
- 🖱️ Integration ins Windows-Kontextmenü via Registry-Datei

---

## Voraussetzungen

- Python ≥ 3.7
- `pip` muss verfügbar sein
- `tkinter` für die GUI-Dateiauswahl (optional)
- Optional: `colorama` für farbige Konsolenausgabe

> 🔄 **Automatisches Nachladen**:  
> Fehlen bestimmte Module wie `importlib-metadata` oder `colorama`, werden sie bei Bedarf automatisch nachinstalliert.

> ⚠️ **`tkinter` kann nicht automatisch nachinstalliert werden**, da es nicht über `pip` verfügbar ist.  
> Falls du die GUI-Funktionalität nutzen möchtest, installiere es ggf. manuell:

- Debian/Ubuntu: `sudo apt install python3-tk`  
- Fedora: `sudo dnf install python3-tkinter`  
- Arch: `sudo pacman -S tk`  
- Windows/macOS: In der Regel bereits enthalten (bei vollständiger Python-Installation)

Fehlt `tkinter`, wechselt das Skript automatisch in den textbasierten Modus.

---

## Installation

Einfach das Skript starten:

```bash
python requirements_install.py
```

> `importlib-metadata` wird bei Bedarf automatisch nachinstalliert (für Python < 3.8).

---

## Verwendung

### Interaktiv (GUI-Dateiauswahl)

```bash
python requirements_install.py
```

> Öffnet einen Dateidialog zur Auswahl von `.py`- oder `.txt`-Dateien.

### Kommandozeile

```bash
python requirements_install.py [PFAD ...] [OPTIONEN]
```

Beispiele:

```bash
python requirements_install.py script.py
python requirements_install.py meinprojekt/ --rekursiv
python requirements_install.py a.py b.txt --ja
python requirements_install.py . -r -v
python requirements_install.py *.py --mapping-datei meine_mapping.json
```

### Unterstützte Dateitypen

- `.py`: Analyse aller `import`-Anweisungen mittels AST
- `.txt`: `requirements.txt`-Dateien, verarbeitet via `pip install -r`

### Häufige Optionen

| Option                      | Beschreibung                                                      |
|----------------------------|--------------------------------------------------------------------|
| `--rekursiv`, `-r`         | Durchsucht Verzeichnisse rekursiv                                 |
| `--mapping-datei`          | Benutzerdefinierte Mapping-Datei (JSON)                           |
| `--ja`, `-j`, `-y`         | Automatische Bestätigung (z. B. für Kontextmenü-Aufrufe)           |
| `--wiederholungen`         | Wiederholungsversuche bei Fehlern                                 |
| `--zeitlimit-installation` | Timeout (Sek.) pro Einzelpaket                                    |
| `--zeitlimit-reqs`         | Timeout (Sek.) für `requirements.txt`                             |
| `--verbose`, `-v`          | Detailliertes Logging (DEBUG)                                     |
| `--quiet`, `-q`            | Nur Warnungen und Fehler anzeigen                                 |

---

## Hinweis zur Paket-Erkennung (Mapping)

Manche Importe weichen von ihrem Installationsnamen ab:

| Importname | Paketname für `pip install`   |
|------------|-------------------------------|
| `cv2`      | `opencv-python`               |
| `yaml`     | `PyYAML`                      |
| `bs4`      | `beautifulsoup4`              |
| `PIL`      | `Pillow`                      |

Ein Standard-Mapping ist im Skript enthalten. Zusätzlich kannst du eigene Zuordnungen angeben:

### Beispiel: `mapping.json`

```json
{
  "cv2": "opencv-python",
  "yaml": "PyYAML",
  "bs4": "beautifulsoup4",
  "skimage": "scikit-image"
}
```

### Dateiort

Dein Mapping kannst du z. B. als `mapping.json` speichern und übergeben mit:

```bash
python requirements_install.py --mapping-datei mapping.json script.py
```

> Eine **Beispiel-Mappingdatei** liegt unter:  
> `extras/mapping.json.example`  
> Die verwendete Datei kann bei Bedarf **an einem anderen Ort** abgelegt werden.

---

## 🔧 Windows-Kontextmenü (optional)

Eine Integration in das Windows-Kontextmenü ermöglicht die direkte Ausführung über Rechtsklick.

### Datei:

```plaintext
extras/add_to_contextmenu.reg
```

### Verwendung:

1. Öffne die `.reg`-Datei durch Doppelklick oder importiere sie manuell.
2. Danach erscheint im Explorer das Menü **„Mit Requirements-Installer installieren“**.
3. Es wird automatisch `requirements_install.py` mit `--ja` ausgeführt.

> Die Pfadangabe innerhalb der `.reg`-Datei muss ggf. angepasst werden.  
> Die verwendete Skriptdatei kann außerhalb des `extras`-Verzeichnisses liegen.

---

## Konfiguration

Eine **Beispiel-Konfigurationsdatei** befindet sich unter:

```plaintext
extras/requirements_install.config.example
```

> Die produktive Konfigurationsdatei (`requirements_install.config`) kann sich außerhalb von `extras/` befinden.  
> Sie wird automatisch erkannt, wenn sie sich im gleichen Verzeichnis wie das Skript befindet.

### Inhalt:

```ini
[Pfade]
python_launcher = py.exe
standard_skript_pfad = C:\Skripte\requirements_install.py
mapping_datei = extras/mapping.json

[Verhalten]
wiederholungen = 3
log_level = INFO
pip_upgrade_pruefen = True

[Zeitlimits]
timeout_installation = 90
timeout_requirements = 300
timeout_pip_upgrade = 60
```

---

## Bekannte Einschränkungen

- Dynamisch erzeugte oder bedingte `import`-Anweisungen werden nicht erkannt
- Für manche Pakete sind Systemtools erforderlich (`gcc`, `pg_config`, Visual C++ Build Tools)
- `.pyc`, `.zip`, `.exe` oder gepackte Dateien werden nicht unterstützt

---

## Lizenz

MIT License – siehe Lizenztext am Ende der Datei `requirements_install.py`.

---

© 2025 Sandro Alessi – [GitHub-Profil](https://github.com/SandroAlessi)
