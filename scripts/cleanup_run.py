#!/usr/bin/env python3
"""
Cleanup script per rimuovere test intrusi da una RUN.

Uso:
    python scripts/cleanup_run.py --project silicon-b --run 38
    python scripts/cleanup_run.py --project silicon-b --run 38 --dry-run
    python scripts/cleanup_run.py --project silicon-b --run 38 --keep-prefix TEST_
"""

import argparse
import sys
from pathlib import Path

# Aggiungi root al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.sheets_client import GoogleSheetsClient
from src.config_loader import ConfigLoader


def cleanup_run(project_name: str, run_number: int, keep_prefix: str = "TEST_", dry_run: bool = False):
    """
    Rimuove righe con TEST_ID che non inizia con il prefisso specificato.

    Args:
        project_name: Nome progetto
        run_number: Numero RUN da pulire
        keep_prefix: Prefisso da mantenere (default: TEST_)
        dry_run: Se True, mostra solo cosa verrebbe eliminato
    """
    print(f"\n{'='*60}")
    print(f"CLEANUP RUN {run_number} - Progetto: {project_name}")
    print(f"{'='*60}")
    print(f"Mantengo solo righe con TEST_ID che inizia con: '{keep_prefix}'")
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

    # Trova indice colonna TEST ID (con spazio)
    try:
        test_id_col = header.index("TEST ID")
    except ValueError:
        # Prova anche senza spazio
        try:
            test_id_col = header.index("TEST_ID")
        except ValueError:
            print(f"Errore: colonna TEST ID non trovata. Header: {header[:5]}")
            return False

    print(f"Colonna TEST_ID: {test_id_col} ({header[test_id_col]})")
    print(f"Righe totali (escluso header): {len(rows)}")
    print()

    # Identifica righe da eliminare (dalla fine per non spostare gli indici)
    rows_to_delete = []
    rows_to_keep = []

    for i, row in enumerate(rows):
        test_id = row[test_id_col] if test_id_col < len(row) else ""
        row_num = i + 2  # +2 perché: +1 per 0-index, +1 per header

        if test_id and not test_id.startswith(keep_prefix):
            rows_to_delete.append((row_num, test_id))
        else:
            rows_to_keep.append((row_num, test_id))

    print(f"Righe da MANTENERE: {len(rows_to_keep)}")
    print(f"Righe da ELIMINARE: {len(rows_to_delete)}")
    print()

    if not rows_to_delete:
        print("Nessuna riga da eliminare!")
        return True

    # Mostra righe da eliminare
    print("Righe che verranno eliminate:")
    print("-" * 40)
    for row_num, test_id in rows_to_delete[:20]:  # Mostra max 20
        print(f"  Riga {row_num}: {test_id}")
    if len(rows_to_delete) > 20:
        print(f"  ... e altre {len(rows_to_delete) - 20} righe")
    print()

    if dry_run:
        print("[DRY RUN] Nessuna modifica effettuata.")
        return True

    # Conferma
    confirm = input(f"Eliminare {len(rows_to_delete)} righe? (s/N): ")
    if confirm.lower() != 's':
        print("Operazione annullata.")
        return False

    # Elimina righe (dalla fine per non spostare gli indici)
    print("\nEliminazione in corso...")
    rows_to_delete.sort(reverse=True, key=lambda x: x[0])

    deleted = 0
    for row_num, test_id in rows_to_delete:
        try:
            worksheet.delete_rows(row_num)
            deleted += 1
            if deleted % 10 == 0:
                print(f"  Eliminate {deleted}/{len(rows_to_delete)} righe...")
        except Exception as e:
            print(f"  Errore eliminazione riga {row_num}: {e}")

    print(f"\nCompletato! Eliminate {deleted} righe.")
    print(f"Righe rimanenti: {len(rows_to_keep)}")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Rimuove test intrusi da una RUN su Google Sheets"
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
        "--keep-prefix", "-k",
        default="TEST_",
        help="Prefisso TEST_ID da mantenere (default: TEST_)"
    )
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="Mostra cosa verrebbe eliminato senza modificare"
    )

    args = parser.parse_args()

    success = cleanup_run(
        project_name=args.project,
        run_number=args.run,
        keep_prefix=args.keep_prefix,
        dry_run=args.dry_run
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
