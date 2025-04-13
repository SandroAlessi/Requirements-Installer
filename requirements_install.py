# -*- coding: utf-8 -*-
"""
Skript zur Installation von Python-Abhängigkeiten

Autor: Sandro Alessi
GitHub: https://github.com/SandroAlessi
Version: 2.0.0 (Deutsch)

Beschreibung:
  Analysiert Python-Skripte (.py) und requirements.txt zur
  Identifizierung benötigter Pakete. Prüft installierte Pakete und
  installiert fehlende Abhängigkeiten mittels pip. Beinhaltet Funktionen
  wie Import-zu-Paketnamen-Mapping, rekursive Verzeichnissuche,
  Wiederholungsversuche bei Installationsfehlern und optionale
  GUI-Dateiauswahl. Konfiguriert für Produktionseinsatz und
  Integration ins Windows-Kontextmenü.

Lizenz: MIT License (siehe Lizenztext am Ende der Datei)
"""

import os
import subprocess
import sys
import importlib
import ast
import time
from functools import lru_cache
import argparse
import logging
import json
import collections
import configparser # Für INI-Konfigurationsdatei

# --- Abhängigkeits-Check & Setup: Colorama (Optional für farbige Logs) ---
try:
    import colorama
    # Initialisiert Colorama für Windows und setzt Auto-Reset
    colorama.init(autoreset=True)
    USE_COLOR = True
except ImportError:
    # Colorama nicht verfügbar, fahre ohne farbige Ausgabe fort
    USE_COLOR = False

# --- Globale Variablen / Konfiguration (werden aus Datei geladen) ---
# Standardwerte, falls Konfigurationsdatei fehlt oder unvollständig ist
DEFAULT_KONFIG = {
    'Pfade': {
        'python_launcher': 'py.exe',
        'standard_skript_pfad': 'C:\\Skripte\\requirements_install.py',
        'mapping_datei': ''
    },
    'Verhalten': {
        'wiederholungen': '3',
        'log_level': 'INFO',
        'pip_upgrade_pruefen': 'True'
    },
    'Zeitlimits': {
        'timeout_installation': '90',
        'timeout_requirements': '300',
        'timeout_pip_upgrade': '60'
    }
}
# ConfigParser-Instanz zum Halten der geladenen Konfiguration
konfiguration = configparser.ConfigParser()

# --- Farbiger Logging Formatter ---
class FarbigerFormatter(logging.Formatter):
    """ Benutzerdefinierter Log-Formatter, der Farben hinzufügt, wenn Colorama verfügbar ist. """
    # Mapping von englischen Level-Namen zu deutschen Bezeichnungen für die Ausgabe
    level_name_german_map = {
        'DEBUG': 'DEBUG',
        'INFO': 'INFO',
        'WARNING': 'WARNUNG',
        'ERROR': 'FEHLER',
        'CRITICAL': 'KRITISCH'
    }

    if USE_COLOR:
        # Farbcodes für verschiedene Log-Level
        LEVEL_FARBEN = {
            logging.DEBUG: colorama.Fore.CYAN,
            logging.INFO: colorama.Fore.GREEN,
            logging.WARNING: colorama.Fore.YELLOW,
            logging.ERROR: colorama.Fore.RED,
            logging.CRITICAL: colorama.Fore.RED + colorama.Style.BRIGHT,
        }
        # Code zum Zurücksetzen der Farbe nach der Ausgabe
        RESET_FARBE = colorama.Style.RESET_ALL
    else:
        # Keine Farben, wenn Colorama nicht importiert werden konnte
        LEVEL_FARBEN = {}
        RESET_FARBE = ""

    def format(self, record):
        """ Formatiert den Log-Eintrag mit Zeitstempel, Level und Nachricht, fügt Farben hinzu. """
        farbe = self.LEVEL_FARBEN.get(record.levelno, "") # Farbe basierend auf Level holen
        # Übersetzten Levelnamen für die Formatierung verwenden
        record.levelname_german = self.level_name_german_map.get(record.levelname, record.levelname)
        # Temporär den Levelnamen im Record ersetzen, um den Formatter korrekt anzuwenden
        original_levelname = record.levelname
        record.levelname = record.levelname_german
        nachricht = super().format(record) # Nachricht mit deutschem Levelnamen formatieren
        record.levelname = original_levelname # Ursprünglichen Levelnamen wiederherstellen

        # Teile die formatierte Nachricht auf, um Farbe gezielter anzuwenden
        teile = nachricht.split(' - ', 2)
        if len(teile) == 3:
            zeitstempel, levelname_formatiert, msg = teile
            # Nur Levelname und Nachricht einfärben
            farbige_nachricht = f"{zeitstempel} - {farbe}{levelname_formatiert}{self.RESET_FARBE} - {farbe}{msg}{self.RESET_FARBE}"
        else:
            # Fallback: Gesamte Zeile einfärben
            farbige_nachricht = f"{farbe}{nachricht}{self.RESET_FARBE}"
        return farbige_nachricht

# --- Standard-Konfiguration & Konstanten ---
# Standard-Mapping von Importnamen zu PyPI-Paketnamen. Kann durch Config-Datei erweitert/überschrieben werden.
STANDARD_IMPORT_ZU_PAKET_MAP = {
    "cv2": "opencv-python", "yaml": "PyYAML", "bs4": "beautifulsoup4",
    "skimage": "scikit-image", "sklearn": "scikit-learn", "PIL": "Pillow",
    "pandas": "pandas", "numpy": "numpy", "scipy": "scipy",
    "matplotlib": "matplotlib", "requests": "requests", "flask": "Flask",
    "django": "Django",
}
# Heuristische Liste: Pakete, die oft einen Compiler benötigen (für Warnungen)
BENÖTIGT_COMPILER = ["numpy", "scipy", "pandas", "lxml", "cryptography", "pyzmq", "gevent", "grpcio", "libsass"]
# Heuristische Liste: Pakete, die oft pg_config benötigen (für Warnungen)
BENÖTIGT_PG_CONFIG = ["psycopg2"]

# --- Logging Instanz ---
# Haupt-Logger für das Skript
log = logging.getLogger(__name__)

# --- Abhängigkeits-Check & Setup: importlib.metadata ---
# Notwendig zur Prüfung installierter Pakete. Versucht Standardbibliothek, dann Backport, dann Installation des Backports.
try:
    from importlib import metadata, util # util für find_spec bei tkinter Prüfung benötigt
    from importlib.metadata import PackageNotFoundError
    log.debug("Standardbibliothek importlib.metadata wird verwendet.")
except ImportError:
    log.debug("Standard importlib.metadata nicht gefunden (Python < 3.8?), versuche importlib_metadata Backport...")
    try:
        import importlib_metadata as metadata
        from importlib_metadata import PackageNotFoundError
        # Prüfe separate Verfügbarkeit von importlib.util
        try: from importlib import util
        except ImportError: util = None; log.warning("importlib.util nicht gefunden, Tkinter-Check evtl. unzuverlässig.")
        log.debug("Backport importlib_metadata wird verwendet.")
    except ImportError:
        # Wenn Backport fehlt, versuche Installation
        log.warning("Weder importlib.metadata noch importlib_metadata gefunden.")
        log.info("Versuche, `importlib-metadata` Backport via pip zu installieren...")
        try:
            # Führe Installation möglichst "leise" durch
            subprocess.run([sys.executable, "-m", "pip", "install", "importlib-metadata"],
                           check=True, capture_output=True, text=True, timeout=60)
            import importlib_metadata as metadata
            from importlib_metadata import PackageNotFoundError
            try: from importlib import util
            except ImportError: util = None
            log.info("`importlib-metadata` Backport erfolgreich installiert.")
        except Exception as e:
            # Kritischer Fehler, wenn Installation fehlschlägt
            print(f"KRITISCH: Konnte 'importlib-metadata' nicht installieren: {e}. Paketprüfung ist nicht möglich.", file=sys.stderr)
            sys.exit(1) # Beenden, Kernfunktionalität fehlt

# --- Hilfsfunktionen ---

def lade_konfiguration(config_datei='requirements_install.config'):
    """Lädt die Konfiguration aus der angegebenen INI-Datei."""
    # Finde Pfad relativ zum ausgeführten Skript
    skript_verzeichnis = os.path.dirname(os.path.abspath(__file__))
    config_pfad = os.path.join(skript_verzeichnis, config_datei)
    log.debug(f"Suche Konfigurationsdatei unter: {config_pfad}")

    # Lade zuerst die fest kodierten Standardwerte
    konfiguration.read_dict(DEFAULT_KONFIG)
    log.debug(f"Standardkonfiguration initialisiert.")

    # Versuche, die Datei zu lesen und die Standardwerte zu überschreiben
    try:
        if os.path.exists(config_pfad):
            # Lese die Datei ein
            gelesen = konfiguration.read(config_pfad, encoding='utf-8')
            if gelesen:
                log.info(f"Konfiguration erfolgreich aus '{config_datei}' geladen.")
            else:
                # Datei existiert, konnte aber nicht gelesen werden (selten)
                log.warning(f"Konfigurationsdatei '{config_datei}' gefunden, aber Lesen fehlgeschlagen. Verwende Standardwerte.")
        else:
            # Datei existiert nicht
            log.warning(f"Konfigurationsdatei '{config_datei}' nicht gefunden. Verwende Standardwerte.")
            # Hier könnte optional eine Default-Config erstellt werden
            # log.info(f"Erstelle Standard-Konfigurationsdatei '{config_datei}'...")
            # try:
            #     with open(config_pfad, 'w', encoding='utf-8') as cfgfile:
            #         konfiguration.write(cfgfile)
            # except OSError as e: log.error(f"Fehler beim Erstellen der Default-Konfig: {e}")

    except configparser.Error as e:
        # Fehler beim Parsen der INI-Datei
        log.error(f"Fehler beim Parsen der Konfigurationsdatei '{config_datei}': {e}. Verwende Standardwerte.")
    except Exception as e:
        # Andere unerwartete Fehler beim Laden
        log.error(f"Unerwarteter Fehler beim Laden der Konfiguration aus '{config_datei}'. Verwende Standardwerte.", exc_info=True)

@lru_cache(maxsize=1) # Ergebnis cachen
def gib_stdlib_module():
    """Gibt ein Set der Namen von Standard-Bibliotheksmodulen zurück."""
    log.debug("Ermittle Standard-Bibliotheksmodule...")
    if sys.version_info >= (3, 10):
        # Zuverlässigste Methode ab Python 3.10
        stdlib = sys.stdlib_module_names
        log.debug(f"Ermittelt {len(stdlib)} stdlib Module via sys.stdlib_module_names (Python >= 3.10).")
        return stdlib
    else:
        # Fallback für ältere Versionen: Statische Liste + Dateisystem-Scan
        log.warning("Verwende Fallback-Liste für Standard-Bibliotheksmodule (Python < 3.10). Diese könnte unvollständig sein.")
        # Umfangreiche statische Liste (vollständige Liste hier einfügen)
        stdlib = {
            "__future__", "_abc", "_ast", "_asyncio", "_bisect", "_blake2", "_bootlocale", "_bz2", "_codecs",
            "_collections_abc", "_compat_pickle", "_compression", "_contextvars", "_crypt", "_csv", "_ctypes",
            "_curses", "_datetime", "_dbm", "_decimal", "_elementtree", "_functools", "_gdbm", "_hashlib",
            "_heapq", "_imp", "_io", "_json", "_locale", "_lsprof", "_lzma", "_markupbase", "_md5",
            "_multibytecodec", "_multiprocessing", "_opcode", "_operator", "_osx_support", "_pickle",
            "_posixshmem", "_posixsubprocess", "_py_abc", "_pydecimal", "_pyio", "_queue", "_random",
            "_sha1", "_sha256", "_sha3", "_sha512", "_signal", "_sitebuiltins", "_socket", "_sqlite3",
            "_sre", "_ssl", "_stat", "_statistics", "_string", "_strptime", "_struct", "_symtable", "_thread",
            "_tracemalloc", "_typing", "_uuid", "_warnings", "_weakref", "_weakrefset", "_xxsubinterpreters",
            "_zoneinfo", "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio", "asyncore",
            "atexit", "audioop", "base64", "bdb", "binascii", "binhex", "bisect", "builtins", "bz2",
            "calendar", "cgi", "cgitb", "chunk", "cmath", "cmd", "code", "codecs", "codeop", "collections",
            "colorsys", "compileall", "concurrent", "configparser", "contextlib", "contextvars", "copy",
            "copyreg", "crypt", "csv", "ctypes", "curses", "dataclasses", "datetime", "dbm", "decimal",
            "difflib", "dis", "distutils", "doctest", "email", "encodings", "ensurepip", "enum", "errno",
            "faulthandler", "fcntl", "filecmp", "fileinput", "fnmatch", "formatter", "fractions", "ftplib",
            "functools", "gc", "getopt", "getpass", "gettext", "glob", "graphlib", "grp", "gzip", "hashlib",
            "heapq", "hmac", "html", "http", "idlelib", "imaplib", "imghdr", "imp", "importlib", "inspect",
            "io", "ipaddress", "itertools", "json", "keyword", "lib2to3", "linecache", "locale", "logging",
            "lzma", "mailbox", "mailcap", "marshal", "math", "mimetypes", "mmap", "modulefinder", "msilib",
            "msvcrt", "multiprocessing", "netrc", "nis", "nntplib", "numbers", "operator", "optparse", "os",
            "ossaudiodev", "parser", "pathlib", "pdb", "pickle", "pickletools", "pipes", "pkgutil", "platform",
            "plistlib", "poplib", "posix", "pprint", "profile", "pstats", "pty", "pwd", "py_compile", "pyclbr",
            "pydoc", "pydoc_data", "pyexpat", "queue", "quopri", "random", "re", "readline", "reprlib",
            "resource", "rlcompleter", "runpy", "sched", "secrets", "select", "selectors", "shelve", "shlex",
            "shutil", "signal", "site", "smtpd", "smtplib", "sndhdr", "socket", "socketserver", "spwd",
            "sqlite3", "sre_compile", "sre_constants", "sre_parse", "ssl", "stat", "statistics", "string",
            "stringprep", "struct", "subprocess", "sunau", "symtable", "sys", "sysconfig", "syslog",
            "tabnanny", "tarfile", "telnetlib", "tempfile", "termios", "textwrap", "this", "threading",
            "time", "timeit", "tkinter", "token", "tokenize", "trace", "traceback", "tracemalloc", "tty",
            "turtle", "turtledemo", "types", "typing", "unicodedata", "unittest", "urllib", "uu", "uuid",
            "venv", "warnings", "wave", "weakref", "webbrowser", "winreg", "winsound", "wsgiref", "xdrlib",
            "xml", "xmlrpc", "zipapp", "zipfile", "zipimport", "zlib", "zoneinfo"
        }
        # Dynamischer Scan als Ergänzung (Best-Effort)
        try:
            stdlib_pfad = os.path.dirname(os.__file__) # Pfad zur Standardbibliothek finden
            if stdlib_pfad and os.path.isdir(stdlib_pfad):
                log.debug(f"Scanne dynamisch Standardbibliothek-Pfad: {stdlib_pfad}")
                for name in os.listdir(stdlib_pfad):
                    voller_pfad = os.path.join(stdlib_pfad, name)
                    if name.endswith(".py"): stdlib.add(name[:-3]) # .py Dateien
                    elif os.path.isdir(voller_pfad) and os.path.exists(os.path.join(voller_pfad, '__init__.py')):
                        stdlib.add(name) # Verzeichnisse mit __init__.py
            log.debug("Dynamischer Scan abgeschlossen.")
        except Exception as e:
            log.debug(f"Fehler bei dynamischem Scan der Standardbibliothek: {e}")
        log.debug(f"Verwende Fallback-Liste mit {len(stdlib)} stdlib Modulen (Python < 3.10).")
        return stdlib

def lade_benutzer_mapping(datei_pfad):
    """Lädt benutzerdefiniertes Import->Paket Mapping aus einer JSON-Datei."""
    if not datei_pfad:
        log.debug("Keine benutzerdefinierte Mapping-Datei in Konfiguration angegeben.")
        return {}
    # Überprüfe, ob der Pfad relativ ist und mache ihn absolut zum Skript-Verzeichnis
    if not os.path.isabs(datei_pfad):
        skript_verzeichnis = os.path.dirname(os.path.abspath(__file__))
        datei_pfad = os.path.join(skript_verzeichnis, datei_pfad)

    log.info(f"Versuche benutzerdefiniertes Mapping zu laden aus: {datei_pfad}")
    try:
        with open(datei_pfad, 'r', encoding='utf-8') as f:
            benutzer_map = json.load(f)
        if not isinstance(benutzer_map, dict):
            log.error(f"Mapping-Datei '{datei_pfad}' enthält kein gültiges JSON-Objekt (Dictionary). Ignoriere Datei.")
            return {}
        # Normalisiere Schlüssel (Importnamen) zu Kleinbuchstaben
        normalisierte_map = {k.lower(): v for k, v in benutzer_map.items()}
        log.info(f"Benutzerdefiniertes Mapping aus '{datei_pfad}' erfolgreich geladen ({len(normalisierte_map)} Einträge).")
        return normalisierte_map
    except FileNotFoundError:
        log.error(f"Benutzerdefinierte Mapping-Datei nicht gefunden: '{datei_pfad}'. Ignoriere.")
        return {}
    except json.JSONDecodeError as e:
        log.error(f"Fehler beim Parsen der JSON-Mapping-Datei '{datei_pfad}': {e}. Ignoriere Datei.")
        return {}
    except Exception as e:
        log.error(f"Unerwarteter Fehler beim Laden der Mapping-Datei '{datei_pfad}'. Ignoriere Datei.", exc_info=True)
        return {}

def finde_dateien_in_pfad(pfad_argument, rekursiv=False):
    """
    Findet unterstützte Dateien (.py, .txt) in einem gegebenen Pfad (Datei oder Verzeichnis).
    Gibt eine Liste absoluter Dateipfade zurück.
    """
    gefundene_dateien = []
    abs_pfad = os.path.abspath(pfad_argument) # Arbeite mit absoluten Pfaden
    log.debug(f"Durchsuche Pfad: '{abs_pfad}' (Rekursiv: {rekursiv})")

    if os.path.isfile(abs_pfad):
        # Argument ist eine Datei
        if abs_pfad.lower().endswith((".py", ".txt")):
            log.debug(f"  Gefunden: Unterstützte Datei '{os.path.basename(abs_pfad)}'")
            gefundene_dateien.append(abs_pfad)
        else:
            log.warning(f"Datei '{os.path.basename(abs_pfad)}' hat keine unterstützte Endung (.py, .txt), wird ignoriert.")
    elif os.path.isdir(abs_pfad):
        # Argument ist ein Verzeichnis
        log.info(f"Durchsuche Verzeichnis: '{abs_pfad}' {'rekursiv' if rekursiv else 'nicht-rekursiv'}.")
        if rekursiv:
            # Rekursive Suche: Gehe durch alle Unterverzeichnisse
            for wurzel, _, dateinamen in os.walk(abs_pfad):
                log.debug(f"  Scanne Unterverzeichnis: {wurzel}")
                for dateiname in dateinamen:
                    if dateiname.lower().endswith((".py", ".txt")):
                        datei_pfad = os.path.join(wurzel, dateiname)
                        log.debug(f"    Gefunden: Unterstützte Datei '{dateiname}'")
                        gefundene_dateien.append(datei_pfad)
        else:
            # Nicht-rekursive Suche: Nur die oberste Ebene des Verzeichnisses
            try:
                log.debug(f"  Scanne oberste Ebene von: {abs_pfad}")
                for element in os.listdir(abs_pfad):
                    element_pfad = os.path.join(abs_pfad, element)
                    # Prüfe, ob es eine Datei ist und die Endung passt
                    if os.path.isfile(element_pfad) and element.lower().endswith((".py", ".txt")):
                        log.debug(f"    Gefunden: Unterstützte Datei '{element}'")
                        gefundene_dateien.append(element_pfad)
            except OSError as e:
                # Fehler beim Lesen des Verzeichnisinhalts (z.B. Berechtigungen)
                log.error(f"Fehler beim Lesen des Verzeichnisinhalts von '{abs_pfad}': {e}")
    else:
        # Der angegebene Pfad existiert nicht oder ist weder Datei noch Verzeichnis
        log.error(f"Angegebener Pfad '{pfad_argument}' ist keine gültige Datei oder Verzeichnis.")

    log.debug(f"Insgesamt {len(gefundene_dateien)} unterstützte Dateien in/unter Pfad '{pfad_argument}' gefunden.")
    return gefundene_dateien

@lru_cache(maxsize=1) # Ergebnis cachen für Performance
def gib_installierte_pakete():
    """
    Ruft ein Dictionary ab, das installierte Pakete auf ihre Versionen abbildet.
    Verwendet importlib.metadata und normalisiert Paketnamen (Kleinschreibung, _ zu -).
    Gibt bei Fehlern ein leeres Dictionary zurück.
    """
    installierte_pakete = {}
    log.info("Lese Liste der installierten Pakete via importlib.metadata...")
    try:
        # Hole die Liste aller Distributionen einmalig
        distributionen = list(metadata.distributions())
        log.debug(f"Metadaten für {len(distributionen)} Distributionen gefunden.")
        # Iteriere durch jede Distribution und extrahiere Name/Version
        for dist in distributionen:
            try:
                paket_name = dist.metadata['Name']
                if paket_name: # Stelle sicher, dass der Name existiert
                     # Normalisiere den Namen für konsistente Vergleiche
                     norm_name = paket_name.lower().replace('_', '-')
                     installierte_pakete[norm_name] = dist.version
                else:
                     # Kann bei manchen Setuptools-Konstrukten vorkommen
                     log.debug(f"Distribution ohne 'Name'-Metadaten gefunden: {dist.entry_points}")
            except Exception as inner_e:
                 # Fehler beim Verarbeiten der Metadaten *einer* Distribution abfangen
                 log.warning(f"Metadaten für eine Distribution konnten nicht gelesen werden: {inner_e}")
                 log.debug(f"Details zur betroffenen Distribution (evtl. unvollständig): {dist}")
        log.info(f"  {len(installierte_pakete)} installierte Pakete im aktuellen Python Environment identifiziert: {sys.prefix}")
    except Exception as e:
        # Fängt allgemeine Fehler beim Abrufen der Distributionsliste ab
        log.error("Installierte Pakete konnten nicht umfassend gelesen werden.", exc_info=True)
    return installierte_pakete

def waehle_dateien_gui():
    """
    Öffnet einen grafischen Dateiauswahldialog (setzt Tkinter voraus).
    Erlaubt die Auswahl mehrerer .py und .txt Dateien.
    Gibt ein Tupel der ausgewählten absoluten Pfade oder None bei Fehler/Abbruch zurück.
    """
    try:
        # Prüfe dynamisch zur Laufzeit, ob tkinter verfügbar ist
        importlib.import_module('tkinter')
        from tkinter import filedialog
        import tkinter as tk
        log.debug("Tkinter-Bibliothek erfolgreich für GUI-Dialog geladen.")
    except ImportError:
        # Kritischer Fehler, wenn tkinter fehlt und der Dialog benötigt wird
        log.critical("Der GUI-Dateidialog erfordert das 'tkinter'-Modul, welches nicht gefunden wurde.")
        log.critical("Stellen Sie sicher, dass tkinter für Ihre Python-Umgebung installiert ist.")
        log.critical("(Unter Debian/Ubuntu z.B. mit 'sudo apt-get update && sudo apt-get install python3-tk')")
        log.critical("Alternativ geben Sie die Datei-/Verzeichnispfade direkt auf der Kommandozeile an.")
        return None # Signalisiert, dass der Dialog nicht geöffnet werden konnte

    # Initialisiere Tkinter-Hauptfenster und verstecke es sofort
    root = tk.Tk()
    try:
        root.withdraw()
        log.info("Öffne GUI-Dateiauswahl-Dialog...")
        # Öffne den Dialog zur Auswahl mehrerer Dateien
        datei_pfade = filedialog.askopenfilenames(
            title="Python-Skripte (.py) oder Requirements-Dateien (.txt) auswählen",
            filetypes=[ # Definiere auswählbare Dateitypen
                ('Unterstützte Dateien', '*.py *.txt'),
                ('Python-Skripte', '*.py'),
                ('Requirements-Dateien', '*.txt'),
                ('Alle Dateien', '*.*')
            ]
        )
    finally:
        # Stelle sicher, dass das Tkinter-Fenster immer geschlossen wird, um Ressourcen freizugeben
        log.debug("Schließe (zerstöre) Tkinter-Hauptfenster.")
        root.destroy()

    # Verarbeite das Ergebnis des Dialogs
    if datei_pfade:
        # datei_pfade ist ein Tupel der ausgewählten Pfade
        log.info(f"{len(datei_pfade)} Datei(en) via GUI ausgewählt.")
    else:
        # Der Benutzer hat den Dialog abgebrochen
        log.info("Keine Dateien via GUI ausgewählt (Dialog abgebrochen).")
    # Gibt das Tupel zurück (kann leer sein)
    return datei_pfade


def extrahiere_importe_aus_py(datei_pfad):
    """
    Extrahiert top-level, absolute Importnamen aus einer Python-Datei mittels AST-Parsing.
    Gibt ein Set von Basis-Importnamen zurück (z.B. 'requests' aus 'import requests.auth').
    Behandelt Syntaxfehler tolerant, kann aber Imports nach dem Fehler verpassen.
    """
    importe = set() # Set zum Speichern eindeutiger Importnamen
    log.debug(f"Extrahiere Imports aus Python-Datei: {os.path.basename(datei_pfad)}")
    try:
        # Lese den gesamten Dateiinhalt in den Speicher
        with open(datei_pfad, "r", encoding="utf-8") as py_datei:
            inhalt = py_datei.read()
        # Parse den Inhalt in einen abstrakten Syntaxbaum (AST)
        ast_baum = ast.parse(inhalt, filename=datei_pfad)
    except FileNotFoundError:
        log.error(f"Python-Datei für Import-Extraktion nicht gefunden: {datei_pfad}")
        return set() # Leeres Set zurückgeben
    except OSError as e:
        log.error(f"Fehler beim Lesen der Python-Datei {datei_pfad}: {e}")
        return set()
    except SyntaxError as e:
        # Logge Syntaxfehler mit Zeile/Spalte, wenn verfügbar
        log.warning(f"Syntaxfehler in {datei_pfad} [Zeile {e.lineno}, Spalte {e.offset or '?'}]: {e.msg}.")
        log.warning("Import-Extraktion für diese Datei könnte unvollständig sein.")
        # Versuch, trotzdem einen (möglicherweise partiellen) Baum zu erzeugen
        try: ast_baum = ast.parse(inhalt, filename=datei_pfad)
        except SyntaxError: ast_baum = None # Setze Baum auf None, wenn auch erneutes Parsen fehlschlägt
    except Exception as e:
        # Fange andere mögliche Fehler während des Parsens ab (z.B. Speicherfehler)
        log.error(f"Unerwarteter Fehler beim Parsen der Python-Datei {datei_pfad}", exc_info=True)
        return set()

    # Verarbeite den Baum nur, wenn das Parsen erfolgreich war (oder einen partiellen Baum lieferte)
    if ast_baum:
        # Gehe rekursiv durch alle Knoten des Syntaxbaums
        for knoten in ast.walk(ast_baum):
            if isinstance(knoten, ast.Import):
                # Verarbeitet Anweisungen wie: import paket oder import paket.submodul
                for alias in knoten.names:
                    # Extrahiere nur den Basis-Paketnamen (erster Teil vor dem Punkt)
                    basis_name = alias.name.split('.')[0]
                    importe.add(basis_name)
            elif isinstance(knoten, ast.ImportFrom):
                # Verarbeitet Anweisungen wie: from paket import ... oder from paket.submodul import ...
                # Ignoriere relative Imports (level > 0), da sie sich auf lokale Module beziehen
                # und nicht direkt via pip installierbar sind.
                if knoten.module and knoten.level == 0: # Nur absolute Imports berücksichtigen
                    # Extrahiere den Basis-Paketnamen aus dem 'module'-Attribut
                    basis_name = knoten.module.split('.')[0]
                    importe.add(basis_name)
                # else: Debug-Logging für relative Imports, falls gewünscht:
                # log.debug(f"Ignoriere relativen Import: level={knoten.level}, module={knoten.module} in {datei_pfad}")

    # Logge die gefundenen Basis-Importnamen für diese Datei
    log.debug(f"  Gefundene Basis-Importnamen in {os.path.basename(datei_pfad)}: {importe if importe else 'Keine'}")
    return importe

def pruefe_externe_abhaengigkeit(befehls_argumente, werkzeug_name, pruefe_ausgabe=False):
    """
    Prüft die Verfügbarkeit eines externen Kommandozeilenwerkzeugs durch dessen Ausführung.
    Loggt Warnungen bei Nichtverfügbarkeit oder Fehlern. Gibt True zurück, wenn verfügbar, sonst False.
    """
    try:
        log.debug(f"Prüfe Verfügbarkeit des externen Werkzeugs '{werkzeug_name}' mit Befehl: {' '.join(befehls_argumente)}")
        # Führe den Befehl aus, fange Ausgabe ab, prüfe Rückgabecode (check=True), setze Timeout
        ergebnis = subprocess.run(befehls_argumente, check=True, capture_output=True, text=True, timeout=5)
        log.debug(f"Externes Werkzeug '{werkzeug_name}' erfolgreich gefunden und ausgeführt.")
        # Optional: Logge die Standardausgabe des Befehls für Debug-Zwecke (gekürzt)
        if pruefe_ausgabe:
            stdout_zusammenfassung = ergebnis.stdout[:200] + ('...' if len(ergebnis.stdout) > 200 else '')
            log.debug(f"Ausgabe von '{' '.join(befehls_argumente)}':\n{stdout_zusammenfassung}")
        return True
    except FileNotFoundError:
        # Das ausführbare Programm wurde im Systempfad (PATH) nicht gefunden
        log.warning(f"Externes Werkzeug '{werkzeug_name}' wurde im Systempfad (PATH) nicht gefunden. Ist es korrekt installiert?")
        return False
    except subprocess.TimeoutExpired:
        # Das Kommando hat länger als der Timeout gedauert
        log.warning(f"Zeitüberschreitung bei der Prüfung des externen Werkzeugs '{werkzeug_name}'. Ist es blockiert oder sehr langsam?")
        return False
    except subprocess.CalledProcessError as e:
        # Das Kommando wurde gefunden und ausgeführt, gab aber einen Fehlercode zurück
        log.warning(f"Externes Werkzeug '{werkzeug_name}' wurde mit einem Fehler ausgeführt (Rückgabewert: {e.returncode}).")
        # Logge die Fehlerausgabe (stderr) für die Diagnose
        log.debug(f"Stderr von '{werkzeug_name}': {e.stderr}")
        return False
    except Exception as e:
        # Fange alle anderen unerwarteten Fehler während der Prüfung ab
        log.error(f"Unerwarteter Fehler bei der Prüfung des externen Werkzeugs '{werkzeug_name}'", exc_info=True)
        return False

def installiere_paket(paket_name, wiederholungen=3, verzoegerung=5, zeitlimit=90):
    """
    Installiert ein einzelnes Python-Paket mittels pip. Beinhaltet Wiederholungslogik
    mit exponentiellem Backoff, Timeout und heuristische Prüfungen auf Build-Abhängigkeiten.
    Gibt True bei erfolgreicher Installation zurück, andernfalls False.
    """
    log.info(f"Versuche Installation von Paket: '{paket_name}'")

    # --- Heuristische Vorab-Prüfungen ---
    # Normalisiere den Paketnamen für konsistente Prüfungen
    normalisierter_name = paket_name.lower().replace('_', '-')

    # Prüfe, ob das Paket bekannt dafür ist, einen Compiler zu benötigen
    if normalisierter_name in BENÖTIGT_COMPILER:
        log.debug(f"Paket '{paket_name}' benötigt möglicherweise einen C/C++ Compiler.")
        # Einfache Prüfung auf Anwesenheit gängiger Compiler-Executables im PATH
        if not any(pruefe_externe_abhaengigkeit([compiler, "--version"], compiler) for compiler in ["gcc", "clang", "cl.exe"]):
             log.warning("Kein gängiger C/C++ Compiler (gcc, clang, cl.exe) im PATH gefunden oder ausführbar.")
             log.warning(f"Installation von '{paket_name}' könnte fehlschlagen. Stellen Sie sicher, dass Build-Tools für Ihr Betriebssystem installiert sind.")
             # Plattformspezifische Hinweise geben
             if sys.platform == "win32": log.warning("-> Unter Windows: Installieren Sie 'Build Tools für Visual Studio'.")
             elif sys.platform == "linux": log.warning("-> Unter Debian/Ubuntu: Versuchen Sie 'sudo apt update && sudo apt install build-essential'. Unter Fedora: 'sudo dnf groupinstall \"Development Tools\"'.")
             elif sys.platform == "darwin": log.warning("-> Unter macOS: Installieren Sie die Xcode Command Line Tools: 'xcode-select --install'.")

    # Prüfe, ob das Paket bekannt dafür ist, pg_config zu benötigen
    if normalisierter_name in BENÖTIGT_PG_CONFIG:
        log.debug(f"Paket '{paket_name}' benötigt möglicherweise 'pg_config' von PostgreSQL.")
        if not pruefe_externe_abhaengigkeit(["pg_config", "--version"], "pg_config"):
             log.warning("'pg_config' Kommando nicht im Systempfad (PATH) gefunden oder nicht ausführbar.")
             log.warning(f"Installation von '{paket_name}' könnte fehlschlagen. Stellen Sie sicher, dass die PostgreSQL Development Header/Libraries installiert sind.")
             log.warning("-> Z.B. 'libpq-dev' unter Debian/Ubuntu, 'postgresql-devel' unter Fedora/CentOS.")

    # --- Installationsschleife mit Wiederholungsversuchen ---
    for versuch in range(wiederholungen):
        log.info(f"  Installationsversuch {versuch + 1}/{wiederholungen} für '{paket_name}'...")
        try:
            # Konstruiere das pip install Kommando
            # --disable-pip-version-check: Unterdrückt die Warnung bzgl. einer neueren pip-Version
            # Optional: --no-cache-dir kann bei Problemen mit korruptem Cache helfen, verlangsamt aber ggf. die Installation
            befehl = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", paket_name]
            log.debug(f"  Führe Kommando aus: {' '.join(befehl)}")

            # Führe das Kommando mittels subprocess.run aus
            ergebnis = subprocess.run(befehl, check=True, capture_output=True, text=True, timeout=zeitlimit)

            # Wenn check=True keinen Fehler auslöst, war die Installation erfolgreich
            log.info(f"  Paket '{paket_name}' erfolgreich installiert.")
            # Logge die Standardausgabe von pip für Debugging-Kontext (optional)
            log.debug(f"  Pip stdout für '{paket_name}':\n{ergebnis.stdout}")
            return True # Signalisiere Erfolg

        except subprocess.CalledProcessError as e:
            # pip-Kommando wurde beendet, aber mit einem Fehlercode (ungleich 0)
            log.error(f"Installation fehlgeschlagen für '{paket_name}' (Versuch {versuch + 1}/{wiederholungen}, Rückgabewert: {e.returncode}):")
            stderr_klein = e.stderr.lower() if e.stderr else "" # Konvertiere stderr zu Kleinbuchstaben für einfachere Textsuche

            # Versuche, gängige Fehler anhand des stderr-Inhalts zu diagnostizieren
            if "permission denied" in stderr_klein or "errno 13" in stderr_klein:
                log.error("  -> Diagnose: Berechtigungsproblem. Mit Administrator-/Root-Rechten versuchen oder Berechtigungen des Installationsziels prüfen.")
            elif "failed building wheel" in stderr_klein or ("error: command" in stderr_klein and "failed with exit status" in stderr_klein):
                 log.error("  -> Diagnose: Fehler beim Erstellen des Wheels (Kompilieren). Fehlen Build-Werkzeuge (Compiler, Header) oder paketspezifische Systembibliotheken?")
                 log.error("     Prüfen Sie die vollständige Fehlermeldung unten auf spezifische Hinweise zu benötigten Komponenten.")
            elif "could not find a version that satisfies the requirement" in stderr_klein:
                 log.error(f"  -> Diagnose: Paket '{paket_name}' (oder eine kompatible Version) nicht auf PyPI gefunden. Tippfehler im Paketnamen oder Netzwerk-/Index-Server-Problem?")
            elif any(term in stderr_klein for term in ["network is unreachable", "connection timed out", "could not resolve host", "proxy error", "ssl:", "tls "]):
                 log.error("  -> Diagnose: Netzwerkfehler. Internetverbindung, DNS-Auflösung, Proxy-Einstellungen oder SSL/TLS-Zertifikate prüfen.")
            elif "pg_config executable not found" in stderr_klein:
                 log.error("  -> Diagnose: 'pg_config' nicht gefunden (benötigt von psycopg2). PostgreSQL Development Header installieren und sicherstellen, dass 'pg_config' im PATH ist.")
            elif "microsoft visual c++" in stderr_klein and "is required" in stderr_klein:
                 log.error("  -> Diagnose: Microsoft Visual C++ Build Tools werden benötigt, wurden aber nicht gefunden. Installieren Sie sie von der Microsoft-Website.")
            else:
                 # Generischer Fehler, wenn kein spezifisches Muster erkannt wurde
                 log.error("  -> Diagnose: Unbekannter pip Installationsfehler. Konsultieren Sie die vollständige Fehlermeldung unten.")

            # Logge immer die vollständige stderr-Ausgabe für detaillierte Fehlerbehebung
            log.error(f"  Vollständige pip Fehlerausgabe (stderr):\n------\n{e.stderr}\n------")

            # Entscheide, ob ein Wiederholungsversuch sinnvoll ist
            if versuch < wiederholungen - 1:
                # Implementiere exponentielles Backoff vor dem nächsten Versuch
                wartezeit = verzoegerung * (2 ** versuch) # z.B. 5s, 10s, 20s, ...
                log.warning(f"  Warte {wartezeit} Sekunden vor dem nächsten Versuch...")
                time.sleep(wartezeit)
            else:
                # Alle Wiederholungsversuche sind fehlgeschlagen
                log.critical(f"Installation von '{paket_name}' nach {wiederholungen} Versuchen endgültig fehlgeschlagen.")
                return False # Signalisiere endgültigen Fehlschlag

        except subprocess.TimeoutExpired:
            # Das pip-Kommando hat länger gedauert als das festgelegte Zeitlimit
            log.error(f"Zeitüberschreitung ({zeitlimit}s) während der Installation von '{paket_name}' (Versuch {versuch + 1}/{wiederholungen}).")
            if versuch < wiederholungen - 1:
                 # Exponentielles Backoff auch bei Timeout anwenden
                 wartezeit = verzoegerung * (2 ** versuch)
                 log.warning(f"  Warte {wartezeit} Sekunden vor dem nächsten Versuch...")
                 time.sleep(wartezeit)
            else:
                 log.critical(f"Installation von '{paket_name}' nach {wiederholungen} Zeitüberschreitungen fehlgeschlagen.")
                 return False # Signalisiere endgültigen Fehlschlag

        except Exception as e:
            # Fange alle anderen unerwarteten Fehler während des Installationsprozesses ab
            log.critical(f"Unerwarteter Fehler während des Installationsversuchs für '{paket_name}'", exc_info=True)
            return False # Signalisiere Fehlschlag bei unerwarteten Problemen

    # Fallback-Rückgabewert, sollte technisch nicht erreicht werden, wenn die Schleifenlogik korrekt ist
    return False

def installiere_aus_requirements(datei_pfad, wiederholungen=2, verzoegerung=5, zeitlimit=300):
    """
    Installiert Pakete aus einer Requirements-Datei mittels `pip install -r <datei>`.
    Beinhaltet einfache Wiederholungslogik für transiente Fehler (z.B. Netzwerk).
    Gibt True bei Erfolg zurück, andernfalls False.
    """
    log.info(f"Verarbeite Requirements-Datei: {os.path.basename(datei_pfad)}")
    # Konstruiere das Basis-pip-Kommando
    basis_befehl = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-r", datei_pfad]

    for versuch in range(wiederholungen):
        log.info(f"  Versuch {versuch + 1}/{wiederholungen}, installiere aus '{os.path.basename(datei_pfad)}'...")
        try:
            # Führe das Kommando aus
            ergebnis = subprocess.run(basis_befehl, check=True, capture_output=True, text=True, timeout=zeitlimit)
            # Erfolg, wenn check=True keine Exception ausgelöst hat
            log.info(f"  Requirements-Datei '{os.path.basename(datei_pfad)}' erfolgreich verarbeitet (Pakete installiert/aktuell).")
            # Logge die stdout für Debugging-Zwecke
            log.debug(f"  Pip stdout für '{os.path.basename(datei_pfad)}':\n{ergebnis.stdout}")
            return True # Signalisiere Erfolg

        except FileNotFoundError:
            # Die angegebene Requirements-Datei wurde nicht gefunden
            log.error(f"Requirements-Datei nicht gefunden unter Pfad: {datei_pfad}")
            return False # Kein Sinn in Wiederholung, wenn die Datei fehlt

        except subprocess.CalledProcessError as e:
            # Der Befehl `pip install -r` ist fehlgeschlagen
            log.error(f"Fehler bei Installation aus '{os.path.basename(datei_pfad)}' (Versuch {versuch + 1}/{wiederholungen}, Rückgabewert: {e.returncode}):")
            # Logge die vollständige stderr, da die Fehlerdiagnose bei '-r' komplex sein kann
            log.error(f"  Vollständige pip Fehlerausgabe (stderr):\n------\n{e.stderr}\n------")
            # Wiederholungslogik für potenziell transiente Probleme
            if versuch < wiederholungen - 1:
                wartezeit = verzoegerung * (2 ** versuch)
                log.warning(f"  Warte {wartezeit} Sekunden vor nächstem Versuch...")
                time.sleep(wartezeit)
            else:
                log.critical(f"Verarbeitung der Requirements-Datei '{os.path.basename(datei_pfad)}' nach {wiederholungen} Versuchen endgültig fehlgeschlagen.")
                return False # Signalisiere endgültigen Fehlschlag

        except subprocess.TimeoutExpired:
            # Die Installation aus der Requirements-Datei hat zu lange gedauert
            log.error(f"Zeitüberschreitung ({zeitlimit}s) während Installation aus '{os.path.basename(datei_pfad)}' (Versuch {versuch + 1}/{wiederholungen}).")
            if versuch < wiederholungen - 1:
                 wartezeit = verzoegerung * (2 ** versuch)
                 log.warning(f"  Warte {wartezeit} Sekunden vor nächstem Versuch...")
                 time.sleep(wartezeit)
            else:
                 log.critical(f"Verarbeitung der Requirements-Datei '{os.path.basename(datei_pfad)}' nach {wiederholungen} Zeitüberschreitungen fehlgeschlagen.")
                 return False # Signalisiere endgültigen Fehlschlag

        except Exception as e:
             # Fange andere unerwartete Fehler ab
             log.critical(f"Unerwarteter Fehler bei Verarbeitung der Requirements-Datei '{os.path.basename(datei_pfad)}'", exc_info=True)
             return False # Signalisiere Fehlschlag

    # Fallback-Rückgabewert
    return False

def aktualisiere_pip(zeitlimit=60):
    """Versucht, die aktuell verwendete pip-Instanz auf die neueste Version von PyPI zu aktualisieren."""
    log.info("Prüfe auf Pip-Aktualisierungen und versuche ggf. Upgrade...")
    try:
        # Kommando zum Aktualisieren von pip selbst
        befehl = [sys.executable, "-m", "pip", "install", "--upgrade", "pip", "--disable-pip-version-check"]
        log.debug(f"Führe Pip-Upgrade-Kommando aus: {' '.join(befehl)}")
        ergebnis = subprocess.run(befehl, check=True, capture_output=True, text=True, timeout=zeitlimit)

        # Analysiere stdout, um eine informativere Log-Nachricht zu geben
        stdout_klein = ergebnis.stdout.lower()
        if "successfully installed pip" in stdout_klein:
             log.info("Pip wurde erfolgreich auf die neueste Version aktualisiert.")
        elif "requirement already satisfied" in stdout_klein or "requirement already up-to-date" in stdout_klein :
             log.info("Pip ist bereits auf dem neuesten Stand.")
        else:
             # Wenn die Ausgabe nicht den erwarteten Mustern entspricht, aber der Befehl erfolgreich war
             log.info("Pip-Aktualisierungsbefehl erfolgreich ausgeführt (keine spezifische Update-Meldung erkannt).")
             log.debug(f"Pip Update Ausgabe:\n{ergebnis.stdout}")

    except subprocess.CalledProcessError as e:
        # Behandelt Fehler spezifisch während des Upgrade-Versuchs
        log.error(f"Fehler beim Aktualisieren von pip (Rückgabewert: {e.returncode}):")
        log.error(f"  Befehl: {' '.join(e.cmd)}")
        log.error(f"  Pip Fehlerausgabe (stderr):\n------\n{e.stderr}\n------")
    except FileNotFoundError:
        # Das pip-Kommando selbst konnte nicht gefunden werden
        log.error("Konnte Kommando 'pip' nicht ausführen. Ist Python/pip korrekt installiert und im Systempfad (PATH) konfiguriert?")
    except subprocess.TimeoutExpired:
        # Der Upgrade-Versuch hat das Zeitlimit überschritten
        log.error("Zeitüberschreitung während des Versuchs, pip zu aktualisieren.")
    except Exception as e:
        # Fängt alle anderen unerwarteten Fehler während des Upgrades ab
        log.error("Ein unerwarteter Fehler ist während der Pip-Aktualisierung aufgetreten", exc_info=True)

def drucke_finale_zusammenfassung(zusammenfassungs_daten):
    """Gibt eine detaillierte Zusammenfassung der Skriptaktionen und Ergebnisse am Ende aus."""
    log.info("\n" + "=" * 30 + " Finale Ausführungszusammenfassung " + "=" * 30)

    # --- Ignorierte / Ungültige Pfade ---
    if zusammenfassungs_daten['ungueltige_pfade']:
        log.warning("Folgende ungültige Pfade oder nicht unterstützte Dateien wurden ignoriert:")
        # Sortiere für konsistente Ausgabe
        for pfad in sorted(zusammenfassungs_daten['ungueltige_pfade']):
            log.warning(f"  - {pfad}")

    # --- Zusammenfassung Requirements-Dateien ---
    log.info("\n--- Verarbeitung Requirements-Dateien (.txt) ---")
    if not zusammenfassungs_daten['verarbeitete_reqs']:
        log.info("Keine Requirements-Dateien (.txt) zur Verarbeitung gefunden oder angegeben.")
    else:
        # Sortiere nach Dateipfad für konsistente Ausgabe
        for datei_pfad, status in sorted(zusammenfassungs_daten['verarbeitete_reqs'].items()):
            basisname = os.path.basename(datei_pfad)
            if status == 'success':
                log.info(f"  [OK]   Erfolgreich verarbeitet: '{basisname}'")
            else: # status == 'failed'
                log.error(f"  [FEHLER] Verarbeitung fehlgeschlagen: '{basisname}' (Details siehe Log oben)")

    # --- Zusammenfassung Pakete aus .py-Dateien ---
    log.info("\n--- Verarbeitung Pakete aus Python-Dateien (.py) ---")
    if not zusammenfassungs_daten['verarbeitete_py_pakete']:
         log.info("Keine Pakete aus .py-Dateien verarbeitet (keine .py-Dateien analysiert oder keine externen Imports gefunden).")
    else:
        # Zeige Statistiken zum Analyseprozess
        log.info(f"  Gefunden: {zusammenfassungs_daten['gesamt_py_importe']} eindeutige Top-Level Importnamen in allen verarbeiteten .py-Dateien.")
        log.info(f"  Ignoriert (StdLib): {zusammenfassungs_daten['uebersprungen_stdlib']} Name(n) als Standard-Bibliotheksmodule erkannt.")
        log.info(f"  Identifizierte Pakete: {zusammenfassungs_daten['gesamt_gemappt']} potenzielle externe Paket(e) nach Mapping/Normalisierung.")

        # Liste Pakete, die übersprungen wurden, da bereits installiert
        if zusammenfassungs_daten['uebersprungen_bereits_installiert']:
            log.info("\n  Folgende identifizierte Pakete waren bereits installiert:")
            # Sortiere nach Paketnamen für Übersichtlichkeit
            for paket, version in sorted(zusammenfassungs_daten['uebersprungen_bereits_installiert'].items()):
                log.info(f"    - {paket} (Installierte Version: {version})")

        # Liste Pakete, die erfolgreich installiert oder als aktuell verifiziert wurden
        if zusammenfassungs_daten['erfolgreiche_installationen_py']:
            log.info("\n  Folgende Pakete wurden erfolgreich installiert oder als aktuell verifiziert:")
            # Sortiere nach Paketnamen
            for paket in sorted(zusammenfassungs_daten['erfolgreiche_installationen_py']):
                log.info(f"    - {paket}")

        # Liste Pakete, bei denen die Installation fehlgeschlagen ist
        if zusammenfassungs_daten['fehlgeschlagene_installationen_py']:
            log.error("\n  Installation FEHLGESCHLAGEN für folgende Pakete (Details siehe Log oben):")
            # Sortiere nach Paketnamen
            for paket in sorted(zusammenfassungs_daten['fehlgeschlagene_installationen_py']):
                log.error(f"    - {paket}")

    # --- Ende der Zusammenfassung ---
    log.info("=" * (60 + len(" Finale Ausführungszusammenfassung ")))


# --- Hauptausführungslogik ---
def haupt():
    """Parst Kommandozeilenargumente, lädt Konfiguration, orchestriert Dateianalyse und Paketinstallation."""

    # --- Lade Konfiguration aus INI-Datei ---
    # Dies geschieht früh, um Defaults für Argument Parser zu haben
    lade_konfiguration() # Lädt Konfiguration in globales 'konfiguration' Objekt

    # --- Argument Parser Setup ---
    # Definiert Kommandozeilenargumente und -optionen
    parser = argparse.ArgumentParser(
        description="Installiert Python-Abhängigkeiten aus .py oder .txt Dateien.",
        formatter_class=argparse.RawDescriptionHelpFormatter, # Behält Formatierung im Hilfetext bei
        epilog="""Beispiele:
  %(prog)s                             # Öffnet GUI Dateidialog (interaktiv, falls Tkinter verfügbar)
  %(prog)s --rekursiv mein_projekt/    # Verarbeitet mein_projekt/ rekursiv
  %(prog)s datei.py req.txt --ja       # Verarbeitet Dateien ohne Bestätigung
  %(prog)s -r -v .                     # Verarbeitet aktuelles Verzeichnis rekursiv mit detaillierter Ausgabe
  %(prog)s --mapping-datei map.json *.py # Nutzt benutzerdefiniertes Mapping
"""
    )

    # Positionales Argument für Eingabepfade (kann 0 oder mehr sein)
    parser.add_argument(
        'pfade',
        metavar='PFAD',
        nargs='*', # Erlaubt keine, eine oder mehrere Angaben
        help="Ein oder mehrere Datei- (.py, .txt) oder Verzeichnispfade zur Verarbeitung. "
             "Wenn keine angegeben werden und das Skript interaktiv läuft, wird ein GUI-Dateidialog geöffnet."
    )

    # Optionale Argumente (Flags und Optionen mit Werten)
    parser.add_argument(
        '--rekursiv', '-r', # Fügt Kurzform '-r' hinzu
        action='store_true', # Speichert True, wenn Flag vorhanden ist
        help="Durchsuche angegebene Verzeichnisse rekursiv nach .py und .txt Dateien."
    )
    parser.add_argument(
        '--mapping-datei',
        metavar='JSON_DATEI', # Aussagekräftiger Platzhalter im Hilfetext
        # Default wird aus der Konfigurationsdatei gelesen
        default=konfiguration.get('Pfade', 'mapping_datei', fallback=None),
        help="Pfad zu einer benutzerdefinierten JSON-Datei mit Import-zu-Paket-Mappings."
             " Benutzermap überschreibt interne Standard-Mappings."
    )
    parser.add_argument(
        '--ja', '-j', '-y', # Fügt gängige Kurzformen hinzu
        action='store_true',
        help="Bestätigung vor der Installation automatisch überspringen."
             " (Wird durch den Registry-Kontextmenü-Eintrag automatisch gesetzt)."
    )
    # Konfigurierbare Optionen mit Defaults aus der INI-Datei
    parser.add_argument(
        '--wiederholungen',
        type=int,
        # Lese Default aus Config, falle auf 3 zurück, wenn nicht vorhanden/lesbar
        default=konfiguration.getint('Verhalten', 'wiederholungen', fallback=3),
        metavar='ANZAHL',
        help="Maximale Anzahl von Installationsversuchen pro Paket oder Requirements-Datei (Standard: %(default)s)."
    )
    parser.add_argument(
        '--zeitlimit-installation',
        type=int,
        default=konfiguration.getint('Zeitlimits', 'timeout_installation', fallback=90),
        metavar='SEKUNDEN',
        help="Zeitlimit in Sekunden für die Installation eines *einzelnen* Pakets (Standard: %(default)s s)."
    )
    parser.add_argument(
        '--zeitlimit-reqs',
        type=int,
        default=konfiguration.getint('Zeitlimits', 'timeout_requirements', fallback=300),
        metavar='SEKUNDEN',
        help="Zeitlimit in Sekunden für die Installation aus einer *Requirements*-Datei (Standard: %(default)s s)."
    )
    # Optionen zur Steuerung der Ausführlichkeit (Log-Level)
    parser.add_argument(
        '-v', '--verbose', '--ausfuehrlich', # Deutsche Alias hinzugefügt
        action='store_const', # Setzt einen konstanten Wert, wenn Flag vorhanden
        dest='loglevel_arg',  # Zielattribut im args-Objekt
        const=logging.DEBUG,  # Wert für "verbose"
        help="Aktiviere ausführliche Debug-Ausgabe (DEBUG Log-Level)."
    )
    parser.add_argument(
        '-q', '--quiet', '--leise', # Deutsche Alias hinzugefügt
        action='store_const',
        dest='loglevel_arg',
        const=logging.WARNING, # Wert für "quiet"
        help="Unterdrücke informative Nachrichten (zeige nur WARNUNG, FEHLER, KRITISCH)."
    )
    # Option zum Überspringen des Pip-Upgrades
    parser.add_argument(
        '--pip-upgrade-ueberspringen',
        action='store_true',
        # Default basiert auf dem negierten Wert aus der Config
        default=not konfiguration.getboolean('Verhalten', 'pip_upgrade_pruefen', fallback=True),
        help="Überspringe die abschließende Prüfung und potenzielle Aktualisierung von pip."
    )

    # Parse die übergebenen Kommandozeilenargumente
    args = parser.parse_args()

    # --- Logging Konfiguration finalisieren ---
    # Bestimme den finalen Log-Level: Kommandozeile (-v/-q) hat Vorrang vor Config-Datei
    config_log_level_str = konfiguration.get('Verhalten', 'log_level', fallback='INFO').upper()
    config_log_level = getattr(logging, config_log_level_str, logging.INFO) # Fallback auf INFO
    # Wenn -v oder -q angegeben wurde, nutze diesen Level, sonst den aus der Config
    final_log_level = args.loglevel_arg if args.loglevel_arg else config_log_level

    # Konfiguriere den Handler und Formatter
    handler = logging.StreamHandler(sys.stdout) # Logge auf die Standardausgabe
    # Nutze den Farb-Formatter (der bei Bedarf auf non-color zurückfällt)
    formatter = FarbigerFormatter('%(asctime)s - %(levelname_german)-8s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    handler.setFormatter(formatter)
    # Füge Handler nur hinzu, wenn noch keiner existiert (verhindert doppelte Logs bei Reload/Import)
    if not log.hasHandlers():
        log.addHandler(handler)
    # Setze den final bestimmten Log-Level
    log.setLevel(final_log_level)

    log.debug("Logging konfiguriert.")
    log.debug(f"Unverarbeitete Kommandozeilenargumente: {sys.argv}")
    log.debug(f"Geparste Argumente: {args}")
    log.debug(f"Finaler Log-Level gesetzt auf: {logging.getLevelName(final_log_level)}")


    # --- Lade & Merge Mappings (final) ---
    # Beginne mit den Standard-Mappings
    aktives_mapping = STANDARD_IMPORT_ZU_PAKET_MAP.copy()
    # Bestimme den Pfad zur Mapping-Datei (Kommandozeile überschreibt Config)
    mapping_datei_pfad = args.mapping_datei # Priorität 1: Kommandozeile
    if not mapping_datei_pfad:
        mapping_datei_pfad = konfiguration.get('Pfade', 'mapping_datei', fallback=None) # Priorität 2: Config

    # Lade das Benutzer-Mapping, falls ein Pfad angegeben ist
    benutzer_mapping = lade_benutzer_mapping(mapping_datei_pfad)
    # Füge Benutzer-Mappings hinzu/überschreibe Defaults (Keys werden in lade_benutzer_mapping kleingeschrieben)
    aktives_mapping.update(benutzer_mapping)
    log.debug(f"Effektives Paket-Mapping (nach Merge mit Benutzerdatei): {aktives_mapping}")


    # --- Sammle zu verarbeitende Dateien ---
    eingabe_pfade = args.pfade # Pfade aus Kommandozeilenargumenten
    # Wenn keine Pfade übergeben wurden, prüfe ob GUI genutzt werden soll/kann
    if not eingabe_pfade:
        ist_interaktiv = sys.stdin.isatty() # Prüfe ob interaktive Sitzung
        log.debug(f"Interaktivitätsprüfung (sys.stdin.isatty()): {ist_interaktiv}")
        if ist_interaktiv:
            log.info("Keine Eingabepfade via Kommandozeile angegeben. Versuche GUI-Dateidialog...")
            gui_ausgewaehlte_pfade = waehle_dateien_gui() # Rufe GUI-Funktion auf
            if gui_ausgewaehlte_pfade:
                eingabe_pfade = list(gui_ausgewaehlte_pfade) # Verwende ausgewählte Pfade
            else:
                 # GUI fehlgeschlagen oder Benutzer hat abgebrochen
                 log.info("Keine Dateien via GUI ausgewählt oder GUI nicht verfügbar. Beende Skript.")
                 sys.exit(0) # Reguläres Ende, keine Arbeit zu tun
        else:
            # Nicht-interaktiv (z.B. Kontextmenü) und keine Pfade -> Fehler
            log.error("Keine Eingabepfade angegeben und nicht im interaktiven Modus. Kann nicht fortfahren.")
            sys.exit(1) # Beenden mit Fehlercode


    # Wenn immer noch keine Pfade vorhanden sind (sollte nur bei GUI-Abbruch passieren)
    if not eingabe_pfade:
        log.info("Keine Dateien oder Verzeichnisse zur Verarbeitung spezifiziert. Beende.")
        sys.exit(0)

    # --- Expandiere Verzeichnisse und validiere Dateien ---
    alle_zu_verarbeitenden_dateien = []
    ungueltige_pfade_zusammenfassung = [] # Sammle ungültige Pfade für die Endzusammenfassung
    log.info("Sammle und validiere zu verarbeitende Dateien/Verzeichnisse...")
    for pfad in eingabe_pfade:
        gefundene_dateien = finde_dateien_in_pfad(pfad, args.rekursiv) # Rufe Expansionsfunktion auf
        if gefundene_dateien:
            alle_zu_verarbeitenden_dateien.extend(gefundene_dateien)
        # Logge Fehler für nicht-existente Pfade etc. innerhalb von finde_dateien_in_pfad
        elif not os.path.exists(pfad):
             # Füge nicht-existente Pfade zur Liste für die Zusammenfassung hinzu
             ungueltige_pfade_zusammenfassung.append(pfad)

    # Entferne Duplikate (z.B. wenn Datei direkt und via Verzeichnis angegeben) und sortiere
    eindeutige_dateien = sorted(list(set(alle_zu_verarbeitenden_dateien)))

    # Früher Ausstieg, wenn nach Expansion keine gültigen Dateien übrig bleiben
    if not eindeutige_dateien:
        log.warning("Keine gültigen .py oder .txt Dateien in den angegebenen Pfaden nach Expansion gefunden.")
        # Gebe Zusammenfassung aus, die nur die ungültigen Pfade listet
        zusammenfassung = collections.defaultdict(list)
        zusammenfassung['ungueltige_pfade'] = ungueltige_pfade_zusammenfassung
        drucke_finale_zusammenfassung(zusammenfassung)
        sys.exit(0) # Reguläres Ende, nichts zu tun

    log.info(f"Verarbeite insgesamt {len(eindeutige_dateien)} eindeutige, unterstützte Datei(en).")


    # --- Initialisiere Zusammenfassungsdaten ---
    # defaultdict(list) ist praktisch zum Anhängen von Elementen ohne vorherige Key-Prüfung
    zusammenfassungs_daten = collections.defaultdict(list)
    zusammenfassungs_daten['ungueltige_pfade'] = ungueltige_pfade_zusammenfassung # Übernehme ignorierte Pfade
    zusammenfassungs_daten['verarbeitete_reqs'] = {} # Speichert: dateipfad -> status ('success'/'failed')
    zusammenfassungs_daten['verarbeitete_py_pakete'] = False # Wird True, wenn .py-Dateien analysiert werden
    zusammenfassungs_daten['erfolgreiche_installationen_py'] = [] # Liste erfolgreicher Installationen aus .py
    zusammenfassungs_daten['fehlgeschlagene_installationen_py'] = [] # Liste fehlgeschlagener Installationen aus .py
    zusammenfassungs_daten['uebersprungen_bereits_installiert'] = {} # Speichert: paket -> version
    zusammenfassungs_daten['uebersprungen_stdlib'] = 0 # Zähler für ignorierte Standard-Module
    zusammenfassungs_daten['gesamt_py_importe'] = 0 # Zähler für gefundene Importe
    zusammenfassungs_daten['gesamt_gemappt'] = 0 # Zähler für Pakete nach Mapping
    gesamterfolg = True # Globaler Flag, wird False bei jedem Fehler


    # ==========================================================================
    # --- Phase 1: Analyse (Identifiziere Abhängigkeiten) ---
    # ==========================================================================
    log.info("\n" + "="*25 + " Phase 1: Analysiere Dateien " + "="*25)
    # Hole aktuelle Systeminformationen
    installierte_pakete_map = gib_installierte_pakete() # Aktuell installierte Pakete
    stdlib_namen = gib_stdlib_module() # Namen der Standard-Module

    # Initialisiere Sammlungen für diese Phase
    gefundene_py_importe = set() # Eindeutige Importnamen aus allen .py-Dateien
    zu_verarbeitende_req_dateien = [] # Liste der Pfade zu .txt-Dateien

    # Iteriere durch die validierten, eindeutigen Dateipfade
    for datei_pfad in eindeutige_dateien:
        dateiname_klein = os.path.basename(datei_pfad).lower()
        if dateiname_klein.endswith(".py"):
            # Extrahiere Imports aus .py-Dateien
            importe = extrahiere_importe_aus_py(datei_pfad)
            gefundene_py_importe.update(importe) # Füge zum Set hinzu
        elif dateiname_klein.endswith(".txt"):
            # Füge .txt-Dateien zur Liste der zu verarbeitenden Requirements hinzu
            zu_verarbeitende_req_dateien.append(datei_pfad)

    # --- Verarbeite gefundene Imports aus .py-Dateien ---
    pakete_aus_py = set() # Eindeutige, normalisierte Paketnamen nach Filterung/Mapping
    zusammenfassungs_daten['gesamt_py_importe'] = len(gefundene_py_importe)
    if gefundene_py_importe:
        zusammenfassungs_daten['verarbeitete_py_pakete'] = True # Markiere, dass .py-Analyse stattfand
        log.info("Filtere Standard-Module und wende Paket-Mappings an...")
        for import_name in gefundene_py_importe:
            # Schritt 1: Ignoriere Standard-Bibliotheksmodule
            if import_name in stdlib_namen:
                log.debug(f"  Ignoriere Standard-Bibliotheksmodul: '{import_name}'")
                zusammenfassungs_daten['uebersprungen_stdlib'] += 1
                continue
            # Schritt 2: Wende Mapping an (benutzerdefiniert überschreibt Standard)
            #             Standardmäßig wird der Importname als Paketname angenommen.
            paket_name = aktives_mapping.get(import_name.lower(), import_name)
            # Schritt 3: Normalisiere den resultierenden Paketnamen
            normalisierter_paket_name = paket_name.lower().replace('_', '-')
            pakete_aus_py.add(normalisierter_paket_name)
            # Logge das Ergebnis des Mappings/Normalisierung
            if import_name.lower() != normalisierter_paket_name:
                 log.debug(f"  Import '{import_name}' --> Paket '{normalisierter_paket_name}' (Mapping/Normalisierung).")
            else:
                 log.debug(f"  Import '{import_name}' --> Paket '{normalisierter_paket_name}' (Direkt übernommen/Normalisiert).")
        zusammenfassungs_daten['gesamt_gemappt'] = len(pakete_aus_py)

    # --- Identifiziere Pakete, die installiert werden müssen ---
    zu_installierende_pakete = set() # Pakete aus .py, die fehlen
    if pakete_aus_py:
        log.info("Prüfe Installationsstatus der identifizierten Pakete aus .py-Dateien...")
        # Vergleiche identifizierte Pakete mit der Liste der installierten Pakete
        for norm_paket_name in sorted(list(pakete_aus_py)):
             if norm_paket_name not in installierte_pakete_map:
                 # Paket fehlt, füge zur Installationsliste hinzu
                 log.info(f"  -> Installation benötigt für: '{norm_paket_name}'")
                 zu_installierende_pakete.add(norm_paket_name)
             else:
                 # Paket ist installiert, speichere für Zusammenfassung
                 version = installierte_pakete_map[norm_paket_name]
                 log.info(f"  Bereits installiert: '{norm_paket_name}' (Version: {version})")
                 zusammenfassungs_daten['uebersprungen_bereits_installiert'][norm_paket_name] = version


    # ==========================================================================
    # --- Phase 2: Zusammenfassung vor Installation & Bestätigung ---
    # ==========================================================================
    log.info("\n" + "="*25 + " Phase 2: Zusammenfassung vor Installation " + "="*25)
    # Bestimme, ob überhaupt Installationsaktionen anstehen
    installations_aktionen_ausstehend = bool(zu_verarbeitende_req_dateien or zu_installierende_pakete)

    if not installations_aktionen_ausstehend:
         log.info("Keine Installationen erforderlich basierend auf der Analyse.")
         # Logge trotzdem ignorierte/ungültige Dateien, falls vorhanden
         if zusammenfassungs_daten['ungueltige_pfade']:
              log.warning("Die folgenden ungültigen Pfade oder nicht unterstützten Dateien wurden ignoriert:")
              for pfad in sorted(zusammenfassungs_daten['ungueltige_pfade']): log.warning(f"  - {pfad}")
    else:
        # Liste die geplanten Aktionen auf
        if zu_verarbeitende_req_dateien:
             log.info("Folgende Requirements-Dateien (.txt) werden verarbeitet:")
             for datei_pfad in sorted(zu_verarbeitende_req_dateien): log.info(f"  - {os.path.basename(datei_pfad)}")
        if zu_installierende_pakete:
             log.info("Folgende Pakete (abgeleitet aus .py-Dateien) erfordern Installation:")
             for paket_name in sorted(list(zu_installierende_pakete)): log.info(f"  - {paket_name}")

        # --- Interaktive Bestätigung ---
        # Überspringe, wenn --ja Flag gesetzt ist (wird durch Registry-Aufruf automatisch gesetzt)
        if not args.ja:
            try:
                # Nutze Standard print für die direkte Benutzeraufforderung
                print("-" * (50 + len(" Phase 2: Zusammenfassung vor Installation "))) # Trennlinie
                bestaetigung = input("Mit den oben genannten Installationsaktionen fortfahren? [j/N]: ")
                # Fahre nur fort, wenn Benutzer explizit 'j' oder 'J' eingibt
                if bestaetigung.lower() != 'j':
                    log.warning("Installation durch Benutzer abgebrochen.")
                    # Gebe die finale Zusammenfassung aus (zeigt, dass nichts installiert wurde)
                    drucke_finale_zusammenfassung(zusammenfassungs_daten)
                    sys.exit(0) # Reguläres Ende, da Benutzerentscheidung
                log.info("Benutzer hat bestätigt. Fahre mit der Installation fort...")
            except EOFError:
                # Fängt Fälle ab, in denen stdin nicht verfügbar ist (z.B. Piping)
                log.error("Interaktive Bestätigung nicht möglich (EOF / Eingabe umgeleitet). Installation abgebrochen.")
                log.error("Verwenden Sie die Option --ja (oder -j / -y) für die nicht-interaktive Ausführung.")
                sys.exit(1) # Fehlerhaft beenden, da Bestätigung nicht eingeholt werden konnte
        else:
             # Das --ja Flag wurde entweder manuell oder durch das Kontextmenü gesetzt
             log.info("Überspringe Bestätigungsaufforderung aufgrund des --ja Flags.")

    log.info("=" * (50 + len(" Phase 2: Zusammenfassung vor Installation ")) + "\n")


    # ==========================================================================
    # --- Phase 3: Installation ---
    # ==========================================================================
    if installations_aktionen_ausstehend:
        log.info("--- Phase 3: Führe Installationen durch ---")

        # --- Verarbeite Requirements-Dateien ---
        gesamt_reqs = len(zu_verarbeitende_req_dateien)
        if zu_verarbeitende_req_dateien:
             log.info(f"Verarbeite {gesamt_reqs} Requirements-Datei(en)...")
             # Sortiere für konsistente Reihenfolge
             for i, req_datei_pfad in enumerate(sorted(zu_verarbeitende_req_dateien)):
                 req_dateiname = os.path.basename(req_datei_pfad)
                 log.info(f"--- Requirements-Datei {i+1}/{gesamt_reqs}: '{req_dateiname}' ---")
                 # Rufe Installationsfunktion für Requirements auf
                 erfolg = installiere_aus_requirements(
                     req_datei_pfad,
                     wiederholungen=args.wiederholungen,
                     verzoegerung=5, # Feste Verzögerung für Requirements
                     zeitlimit=args.zeitlimit_reqs
                 )
                 # Speichere Ergebnis für die Zusammenfassung
                 zusammenfassungs_daten['verarbeitete_reqs'][req_datei_pfad] = 'success' if erfolg else 'failed'
                 if not erfolg:
                     gesamterfolg = False # Setze globalen Erfolgsflag bei Fehlschlag
                     log.error(f"Verarbeitung der Requirements-Datei fehlgeschlagen: '{req_dateiname}'")
             log.info("--- Verarbeitung der Requirements-Dateien abgeschlossen ---")

        # --- Installiere einzelne Pakete aus .py-Dateien ---
        gesamt_py_install = len(zu_installierende_pakete)
        if zu_installierende_pakete:
             log.info(f"Installiere {gesamt_py_install} Paket(e) abgeleitet aus .py-Dateien...")
             # Sortiere Pakete alphabetisch für konsistente Reihenfolge
             sortierte_pakete = sorted(list(zu_installierende_pakete))
             for i, paketname in enumerate(sortierte_pakete):
                 log.info(f"--- Installiere Paket {i+1}/{gesamt_py_install}: '{paketname}' ---")
                 # Rufe Installationsfunktion für einzelne Pakete auf
                 erfolg = installiere_paket(
                     paketname,
                     wiederholungen=args.wiederholungen,
                     verzoegerung=5, # Feste Verzögerung für Einzelpakete
                     zeitlimit=args.zeitlimit_installation
                 )
                 # Speichere Ergebnis für die Zusammenfassung
                 if erfolg:
                     zusammenfassungs_daten['erfolgreiche_installationen_py'].append(paketname)
                 else:
                     zusammenfassungs_daten['fehlgeschlagene_installationen_py'].append(paketname)
                     gesamterfolg = False # Setze globalen Erfolgsflag bei Fehlschlag
                     log.error(f"Installation des Pakets fehlgeschlagen: '{paketname}'")
             log.info("--- Installation der Pakete aus .py-Dateien abgeschlossen ---")

    else:
         # Logge, wenn keine Aktionen nach der Bestätigungsphase nötig waren
         log.info("--- Phase 3: Keine Installationsaktionen durchzuführen ---")


    # ==========================================================================
    # --- Phase 4: Pip Upgrade (Optional) ---
    # ==========================================================================
    # Lese Timeout aus Config oder nutze Fallback
    pip_upgrade_timeout = konfiguration.getint('Zeitlimits', 'timeout_pip_upgrade', fallback=60)
    # Prüfe, ob Upgrade übersprungen werden soll (via Arg oder Config)
    if not args.pip_upgrade_ueberspringen:
        log.info("\n--- Phase 4: Prüfe/Aktualisiere Pip ---")
        aktualisiere_pip(pip_upgrade_timeout) # Rufe Upgrade-Funktion auf
    else:
        log.info("\n--- Phase 4: Überspringe Pip-Aktualisierungsprüfung ---")


    # ==========================================================================
    # --- Phase 5: Finale Zusammenfassung & Beenden ---
    # ==========================================================================
    log.info("\n--- Phase 5: Finale Zusammenfassung ---")
    # Gebe den detaillierten Bericht aus
    drucke_finale_zusammenfassung(zusammenfassungs_daten)

    # Bestimme finalen Exit-Status und Verhalten
    if gesamterfolg:
         log.info("Skript erfolgreich und ohne bekannte Fehler beendet.")
         # Kurze Pause, außer im Quiet-Modus, damit Benutzer letzte Meldung sieht
         # Nützlich insbesondere bei nicht-interaktiven Fenstern (Kontextmenü)
         if final_log_level < logging.WARNING:
              time.sleep(1.5)
         sys.exit(0) # Beende mit Erfolgscode 0
    else:
         log.critical("Skript mit Fehlern beendet.")
         # --- PAUSE IMMER BEI FEHLER ---
         # Hält das Konsolenfenster offen, damit der Benutzer Fehler im Log sehen kann
         print("\nFEHLER AUFGETRETEN. Drücken Sie Enter, um das Fenster zu schließen...", file=sys.stderr)
         try:
             input() # Warte auf Enter-Taste
         except EOFError:
             # Fallback, falls stdin/stderr aus irgendeinem Grund nicht für input() nutzbar sind
             log.debug("EOFError beim Warten auf Eingabe nach Fehler. Warte stattdessen 15 Sekunden.")
             time.sleep(15) # Warte als Fallback eine feste Zeit
         sys.exit(1) # Beende mit Fehlercode 1


# --- Skript-Einstiegspunkt ---
# Wird ausgeführt, wenn das Skript direkt gestartet wird (nicht importiert)
if __name__ == "__main__":
    try:
        # Starte die Hauptausführungslogik
        haupt()
    except KeyboardInterrupt:
        # Fange Strg+C (Benutzerabbruch) sauber ab
        # Nutze print, da Logging evtl. schon beendet/gestört ist
        print("\nAusführung durch Benutzer (Strg+C) abgebrochen.", file=sys.stderr)
        sys.exit(130) # Standard-Exit-Code für Abbruch durch SIGINT
    except Exception as e:
        # Fange alle anderen unerwarteten Fehler auf oberster Ebene ab
        log.critical("Ein unerwarteter, nicht abgefangener kritischer Fehler ist aufgetreten!", exc_info=True)
        # Versuche trotzdem, das Fenster für den Benutzer offen zu halten
        print("\nUNERWARTETER KRITISCHER FEHLER. Drücken Sie Enter, um das Fenster zu schließen...", file=sys.stderr)
        try: input()
        except: time.sleep(15) # Fallback-Pause
        sys.exit(2) # Verwende anderen Fehlercode für unerwartete kritische Fehler

# --- Lizenztext (MIT) ---
# MIT License
#
# Copyright (c) 2025 Sandro Alessi
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.