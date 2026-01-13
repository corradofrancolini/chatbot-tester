#!/usr/bin/env python3
"""
Deduplica script per rimuovere righe duplicate (stesso TEST ID).

Uso:
    python scripts/deduplicate_run.py --project silicon-b --run 38
    python scripts/deduplicate_run.py --project silicon-b --run 38 --dry-run
    python scripts/deduplicate_run.py --project silicon-b --run 38 --keep first  # default
    python scripts/deduplicate_run.py --project silicon-b --run 38 --keep last
"""

import argparse
import sys
import time
from pathlib import Path

# Aggiungi root al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.sheets_client import GoogleSheetsClient
from src.config_loader import ConfigLoader


def deduplicate_run(project_name: str, run_number: int, keep: str = "first", dry_run: bool = False):
    """
    Rimuove righe duplicate (stesso TEST ID), mantenendo la prima o l'ultima.

    Args:
        project_name: Nome progetto
        run_number: Numero RUN da pulire
        keep: "first" o "last" - quale riga mantenere per ogni TEST ID
        dry_run: Se True, mostra solo cosa verrebbe eliminato
    """
    print(f"\n{'='*60}")
    print(f"DEDUPLICATE RUN {run_number} - Progetto: {project_name}")
    print(f"{'='*60}")
    print(f"Strategia: mantieni '{keep}' per ogni TEST ID duplicato")
    print(f"Dry run: {'SI' if dry_run else 'NO'}")
    print()

    # Carica configurazione progetto
    config_loader = ConfigLoader()
    project = config_loader.load_project(project_name)
    if not project:
        print(f"Errore: progetto '{project_name}' non trovato")
        return False

    if not project.google_sheets:
        print("Errore: Google Sheets non configurato per questo progetto")
        return False

    # Inizializza client
    client = GoogleSheetsClient(
        credentials_path=project.google_sheets.credentials_path,
        spreadsheet_id=project.google_sheets.spreadsheet_id,
        drive_folder_id=project.google_sheets.drive_folder_id
    )

    if not client.authenticate():
        print("Errore: impossibile autenticarsi a Google Sheets")
        return False

    print("Autenticazione Google Sheets OK")

    # Trova il foglio della RUN
    worksheet = client.get_run_sheet(run_number)
    if not worksheet:
        print(f"Errore: RUN {run_number} non trovata")
        return False

    print(f"Foglio trovato: {worksheet.title}")

    # Leggi tutti i dati
    all_values = worksheet.get_all_values()
    if len(all_values) < 2:
        print("Foglio vuoto o solo header")
        return True

    header = all_values[0]
    rows = all_values[1:]

    # Trova indice colonna TEST ID
    try:
        test_id_col = header.index("TEST ID")
    except ValueError:
        try:
            test_id_col = header.index("TEST_ID")
        except ValueError:
            print(f"Errore: colonna TEST ID non trovata. Header: {header[:5]}")
            return False

    print(f"Colonna TEST ID: {test_id_col} ({header[test_id_col]})")
    print(f"Righe totali (escluso header): {len(rows)}")
    print()

    # Trova duplicati
    seen = {}  # test_id -> list of (row_num, row_data)
    for i, row in enumerate(rows):
        test_id = row[test_id_col] if test_id_col < len(row) else ""
        row_num = i + 2  # +2 perché: +1 per 0-index, +1 per header

        if test_id:
            if test_id not in seen:
                seen[test_id] = []
            seen[test_id].append(row_num)

    # Identifica righe da eliminare
    rows_to_delete = []
    unique_count = 0
    duplicate_count = 0

    for test_id, row_nums in seen.items():
        if len(row_nums) == 1:
            unique_count += 1
        else:
            duplicate_count += 1
            # Tieni la prima o l'ultima
            if keep == "first":
                to_delete = row_nums[1:]  # elimina tutte tranne la prima
            else:
                to_delete = row_nums[:-1]  # elimina tutte tranne l'ultima

            for row_num in to_delete:
                rows_to_delete.append((row_num, test_id))

    print(f"TEST ID unici: {unique_count}")
    print(f"TEST ID duplicati: {duplicate_count}")
    print(f"Righe da MANTENERE: {len(seen)}")
    print(f"Righe da ELIMINARE: {len(rows_to_delete)}")
    print()

    if not rows_to_delete:
        print("Nessuna riga duplicata da eliminare!")
        return True

    # Mostra alcuni duplicati
    print("Esempi di righe duplicate da eliminare:")
    print("-" * 40)
    shown_ids = set()
    for row_num, test_id in rows_to_delete[:15]:
        if test_id not in shown_ids:
            count = len(seen[test_id])
            print(f"  {test_id}: {count} occorrenze (elimino {count-1})")
            shown_ids.add(test_id)
    if len(rows_to_delete) > 15:
        print(f"  ... e altri")
    print()

    if dry_run:
        print("[DRY RUN] Nessuna modifica effettuata.")
        return True

    # Conferma
    confirm = input(f"Eliminare {len(rows_to_delete)} righe duplicate? (s/N): ")
    if confirm.lower() != 's':
        print("Operazione annullata.")
        return False

    # Elimina righe (dalla fine per non spostare gli indici)
    print("\nEliminazione in corso...")
    rows_to_delete.sort(reverse=True, key=lambda x: x[0])

    deleted = 0
    errors = 0
    for row_num, test_id in rows_to_delete:
        try:
            worksheet.delete_rows(row_num)
            deleted += 1
            if deleted % 10 == 0:
                print(f"  Eliminate {deleted}/{len(rows_to_delete)} righe...")
            # Rate limit: pausa ogni 50 righe
            if deleted % 50 == 0:
                print("  Pausa 30s per rate limit...")
                time.sleep(30)
        except Exception as e:
            errors += 1
            if "429" in str(e):
                print(f"  Rate limit raggiunto dopo {deleted} righe. Attendi e rilancia.")
                break
            print(f"  Errore eliminazione riga {row_num}: {e}")

    print(f"\nCompletato! Eliminate {deleted} righe ({errors} errori).")
    print(f"Righe rimanenti: {len(rows) - deleted + 1}")  # +1 per header

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Rimuove righe duplicate (stesso TEST ID) da una RUN su Google Sheets"
    )
    parser.add_argument(
        "--project", "-p",
        required=True,
        help="Nome del progetto (es. silicon-b)"
    )
    parser.add_argument(
        "--run", "-r",
        type=int,
        required=True,
        help="Numero della RUN da pulire (es. 38)"
    )
    parser.add_argument(
        "--keep", "-k",
        choices=["first", "last"],
        default="first",
        help="Quale riga mantenere per ogni TEST ID duplicato (default: first)"
    )
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="Mostra cosa verrebbe eliminato senza modificare"
    )

    args = parser.parse_args()

    success = deduplicate_run(
        project_name=args.project,
        run_number=args.run,
        keep=args.keep,
        dry_run=args.dry_run
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
