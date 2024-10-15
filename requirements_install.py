import os
import subprocess
import sys
import importlib
import tkinter as tk
from tkinter import filedialog
import ast
import re
import time
from functools import lru_cache

try:
    from importlib import metadata
except ImportError:
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "importlib-metadata"], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"Fehler bei der Installation von importlib-metadata: {e.cmd} mit Rückgabewert {e.returncode}, Fehlerausgabe: {e.stderr}")
        sys.exit(1)
    from importlib import metadata

# Cache für die Ergebnisse von importlib.util.find_spec
@lru_cache(maxsize=None)
def is_package_missing(package):
    return importlib.util.find_spec(package) is None

# Funktion, um sicherzustellen, dass erforderliche Bibliotheken installiert sind
def ensure_required_packages(packages):
    missing_packages = []
    for package in packages:
        if is_package_missing(package):
            missing_packages.append(package)
    
    if missing_packages:
        print("Fehlende Pakete werden installiert: ", ", ".join(missing_packages))
        for package in missing_packages:
            try:
                install(package)
            except subprocess.CalledProcessError as e:
                print(f"Fehler bei der Installation von {package}: {e.cmd} mit Rückgabewert {e.returncode}, Fehlerausgabe: {e.stderr}")
            except Exception as e:
                print(f"Unerwarteter Fehler bei der Installation von {package}: {e}")

# Funktion, um Dateien auszuwählen (Python-Skripte oder requirements.txt)
def select_files():
    root = tk.Tk()
    try:
        root.withdraw()
        # Kombinierte Standardoption und einzelne Typen als optional im Dropdown
        file_paths = filedialog.askopenfilenames(
            title="Dateien auswählen",
            filetypes=[
                ('Python-Skript oder requirements.txt', '*.py;requirements.txt'),  # Standardoption
                ('Python-Skripte', '*.py'),  # Optionale Einzeltypen
                ('requirements.txt', 'requirements.txt')  # Optionale Einzeltypen
            ]
        )
    finally:
        root.destroy()
    return file_paths

# Funktion, um die Importe aus einer Python-Datei zu extrahieren
def extract_imports(file_path):
    try:
        with open(file_path, "r") as file:
            tree = ast.parse(file.read(), filename=file_path)
    except FileNotFoundError:
        print(f"Datei nicht gefunden: {file_path}")
        return set()
    except SyntaxError as e:
        print(f"Syntaxfehler in der Datei {file_path}: {e}")
        return set()
    
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split('.')[0])
    
    return imports

# Funktion, um Pakete aus einer requirements.txt-Datei zu extrahieren
def extract_requirements(file_path):
    with open(file_path, "r") as file:
        packages = [line.strip() for line in file if line.strip() and not line.startswith("#")]
    return packages

# Helper-Funktion, um zu überprüfen, ob eine Datei eine unterstützte Erweiterung hat
def is_supported_file(file_path):
    return os.path.isfile(file_path) and os.path.splitext(file_path)[1].lower() in [".py", ".txt"]

# Funktion, um ein Paket zu installieren, mit einem Retry-Mechanismus
def install(package, retries=3, delay=5, timeout=30):
    # Sicherstellen, dass erforderliche Abhängigkeiten vorhanden sind
    if package == "libsass":
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "setuptools"], check=True, timeout=timeout, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            print(f"Fehler bei der Installation von setuptools: {e.cmd} mit Rückgabewert {e.returncode}, Fehlerausgabe: {e.stderr}")
            return
    
    # Überprüfen, ob systemweite Abhängigkeiten fehlen
    if package in ["libsass", "some_other_package_requiring_compiler"]:
        try:
            result = subprocess.run(["gcc", "--version"], check=True, capture_output=True, text=True)
        except FileNotFoundError:
            print("GCC-Compiler nicht gefunden. Bitte installieren Sie einen C-Compiler, um die Installation von Paketen wie libsass zu ermöglichen.")
            return
        except subprocess.CalledProcessError as e:
            print(f"Fehler beim Überprüfen des GCC-Compilers: {e.cmd} mit Rückgabewert {e.returncode}, Fehlerausgabe: {e.stderr}")
            return
    
    for attempt in range(retries):
        try:
            result = subprocess.run([sys.executable, "-m", "pip", "install", package], check=True, timeout=timeout, capture_output=True, text=True)
            print(result.stdout)
            return
        except subprocess.CalledProcessError as e:
            error_message = e.stderr.lower() if e.stderr else ""
            if "permission" in error_message:
                print(f"Fehler bei der Installation von {package} (Versuch {attempt + 1} von {retries}): Berechtigungsproblem. Versuchen Sie, den Befehl mit Administratorrechten auszuführen.")
            elif "network" in error_message or "connection" in error_message:
                print(f"Fehler bei der Installation von {package} (Versuch {attempt + 1} von {retries}): Netzwerkproblem erkannt. Überprüfen Sie Ihre Internetverbindung.")
            elif "pg_config" in error_message:
                print(f"Fehler bei der Installation von {package} (Versuch {attempt + 1} von {retries}): 'pg_config' nicht gefunden. Bitte stellen Sie sicher, dass PostgreSQL installiert ist und dass 'pg_config' im Systempfad (PATH) enthalten ist.")
            else:
                print(f"Fehler bei der Installation von {package} (Versuch {attempt + 1} von {retries}): {e.cmd} mit Rückgabewert {e.returncode}, Fehlerausgabe: {e.stderr}")
            if attempt < retries - 1:
                time.sleep(delay * (2 ** attempt))  # Exponentieller Backoff
        except subprocess.TimeoutExpired as e:
            print(f"Zeitüberschreitung bei der Installation von {package} (Versuch {attempt + 1} von {retries}): {e}")
            if attempt < retries - 1:
                time.sleep(delay * (2 ** attempt))  # Exponentieller Backoff
        except Exception as e:
            print(f"Unerwarteter Fehler bei der Installation von {package}: {e}")
            break
    print(f"Installation von {package} nach {retries} Versuchen fehlgeschlagen.")

# Funktion, um pip zu aktualisieren, falls eine neue Version verfügbar ist
def upgrade_pip_if_needed():
    try:
        print("Aktualisiere pip...")
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], check=True, capture_output=True, text=True)
        print("pip wurde erfolgreich aktualisiert.")
    except subprocess.CalledProcessError as e:
        print(f"Fehler beim Aktualisieren von pip: {e.cmd} mit Rückgabewert {e.returncode}, Fehlerausgabe: {e.stderr}")
    except Exception as e:
        print(f"Unerwarteter Fehler beim Aktualisieren von pip: {e}")

if __name__ == "__main__":
    # Überprüfe, ob tkinter installiert ist, bevor das Skript ausgeführt wird
    ensure_required_packages(["tkinter"])

    file_paths = select_files()
    if file_paths:
        all_libraries = set()
        for file_path in file_paths:
            if is_supported_file(file_path):
                if file_path.endswith(".py"):
                    all_libraries.update(extract_imports(file_path))
                elif file_path.endswith(".txt"):
                    all_libraries.update(extract_requirements(file_path))
            else:
                print(f"Ungültiger oder nicht unterstützter Dateityp übersprungen: {file_path}")

        # Installiere jede Bibliothek nur einmal
        for lib in all_libraries:
            try:
                metadata.version(lib)
                print(f"{lib} ist bereits installiert.")
            except metadata.PackageNotFoundError:
                print(f"{lib} wird installiert...")
                try:
                    install(lib)
                except subprocess.CalledProcessError as e:
                    print(f"Fehler bei der Installation von {lib}: {e.cmd} mit Rückgabewert {e.returncode}, Fehlerausgabe: {e.stderr}")

        # Aktualisiere pip, falls eine neue Version verfügbar ist
        upgrade_pip_if_needed()