#!/usr/bin/env python3
"""
Completa upload screenshot mancanti per run 34, 35, 36, 37
Versione ottimizzata con batch updates
"""
import os
import sys
import time
import requests
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.sheets_client import GoogleSheetsClient
from src.config_loader import ConfigLoader

# Mapping job_number → run_number
JOB_RUN_MAP = {
    62: 34,  # Pipeline #61
    63: 35,  # Pipeline #62
    64: 36,  # Pipeline #63
    65: 37,  # Pipeline #64
}

CCI_TOKEN = os.environ.get("CIRCLECI_TOKEN", "")

def get_artifacts(job_number: int) -> list[dict]:
    """Ottiene artifacts da job CircleCI"""
    url = f"https://circleci.com/api/v2/project/gh/corradofrancolini/chatbot-tester-private/{job_number}/artifacts"
    resp = requests.get(url, headers={"Circle-Token": CCI_TOKEN})
    return resp.json().get("items", [])

def find_worksheet(client: GoogleSheetsClient, run_number: int):
    """Trova worksheet per run number (nome può avere suffisso)"""
    prefix = f"Run {run_number:03d}"
    for ws in client._spreadsheet.worksheets():
        if ws.title.startswith(prefix):
            return ws
    return None

def process_run(client: GoogleSheetsClient, run_number: int, artifacts: list[dict]):
    """Upload screenshot mancanti e aggiorna sheet"""
    print(f"  Cerco foglio Run {run_number:03d}...", flush=True)
    worksheet = find_worksheet(client, run_number)
    if not worksheet:
        print(f"  ⚠ Foglio non trovato per Run {run_number}")
        return

    sheet_name = worksheet.title
    print(f"  Foglio: {sheet_name}", flush=True)

    # Leggi tutte le righe in un'unica chiamata
    print(f"  Leggo dati...", flush=True)
    all_values = worksheet.get_all_values()
    print(f"  {len(all_values)} righe totali", flush=True)

    # Trova test già con screenshot e mappa test_id → row
    # Colonna F (index 5) = SCREENSHOT
    existing = set()
    test_to_row = {}
    for i, row in enumerate(all_values):
        if row:
            test_id = row[0]
            test_to_row[test_id] = i + 1
            if len(row) > 5 and row[5] and "IMAGE" in str(row[5]).upper():
                existing.add(test_id)

    print(f"  {len(existing)} test già con screenshot", flush=True)

    # Filtra solo screenshot PNG
    screenshots = [a for a in artifacts if a["path"].endswith(".png")]
    print(f"  {len(screenshots)} screenshot disponibili su CircleCI", flush=True)

    # Trova quelli da caricare
    to_upload = []
    for art in screenshots:
        filename = Path(art["path"]).name
        test_id = filename.replace(".png", "")
        if test_id not in existing:
            to_upload.append((test_id, art))

    print(f"  {len(to_upload)} da caricare", flush=True)

    if not to_upload:
        print(f"  ✓ Nessun upload necessario")
        return

    # Trova o crea folder Drive
    folder_name = "silicon-b_screenshots"
    folder_id = None

    results = client._drive_service.files().list(
        q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        spaces='drive',
        fields='files(id, name)'
    ).execute()

    folders = results.get('files', [])
    if folders:
        folder_id = folders[0]['id']
    else:
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = client._drive_service.files().create(body=file_metadata, fields='id').execute()
        folder_id = folder.get('id')

    # Upload tutti gli screenshot e raccogli updates
    from googleapiclient.http import MediaFileUpload

    updates_b = []  # Colonna B (IMAGE)
    updates_c = []  # Colonna C (URL)
    uploaded = 0

    for test_id, art in to_upload:
        try:
            # Download da CircleCI
            resp = requests.get(art["url"], headers={"Circle-Token": CCI_TOKEN})
            if resp.status_code != 200:
                print(f"  ⚠ {test_id}: download failed ({resp.status_code})")
                continue

            # Salva temporaneamente
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(resp.content)
                temp_path = f.name

            # Upload su Drive
            file_metadata = {
                'name': f"{test_id}.png",
                'parents': [folder_id]
            }
            media = MediaFileUpload(temp_path, mimetype='image/png')

            file = client._drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()

            file_id = file.get('id')

            # Rendi pubblico
            client._drive_service.permissions().create(
                fileId=file_id,
                body={'type': 'anyone', 'role': 'reader'}
            ).execute()

            # Cleanup temp file
            os.unlink(temp_path)

            # Prepara update per Sheets
            row_num = test_to_row.get(test_id)
            if row_num:
                thumbnail_url = f"https://drive.google.com/thumbnail?id={file_id}&sz=w400"
                drive_url = f"https://drive.google.com/file/d/{file_id}/view"

                updates_b.append({
                    "range": f"F{row_num}",
                    "values": [[f'=IMAGE("{thumbnail_url}")']]
                })
                updates_c.append({
                    "range": f"G{row_num}",
                    "values": [[drive_url]]
                })

            uploaded += 1
            if uploaded % 10 == 0:
                print(f"  {uploaded}/{len(to_upload)} uploadati", flush=True)

        except Exception as e:
            error_msg = str(e)[:60]
            print(f"  ⚠ {test_id}: {error_msg}")
            if "429" in str(e) or "Quota" in str(e):
                print("  ⏸ Rate limit - pausa 60s")
                time.sleep(60)

    print(f"  Upload completato, aggiorno Sheets...", flush=True)

    # Batch update in blocchi da 50
    def batch_update_cells(updates, col_name):
        for i in range(0, len(updates), 50):
            batch = updates[i:i+50]
            try:
                worksheet.batch_update(batch, value_input_option="USER_ENTERED")
                print(f"    {col_name}: {min(i+50, len(updates))}/{len(updates)}", flush=True)
                time.sleep(1)  # Rate limit
            except Exception as e:
                print(f"  ⚠ Batch update error: {e}")
                time.sleep(30)

    if updates_b:
        batch_update_cells(updates_b, "SCREENSHOT")
    if updates_c:
        batch_update_cells(updates_c, "URL")

    print(f"  ✓ {uploaded} caricati")

def main():
    print("Inizializzazione...", flush=True)

    # Setup client con OAuth (per Drive upload)
    loader = ConfigLoader(".")
    project = loader.load_project("silicon-b")

    client = GoogleSheetsClient(
        credentials_path="config/oauth_credentials.json",
        spreadsheet_id=project.google_sheets.spreadsheet_id,
        drive_folder_id="dummy"  # Needed to init drive service
    )
    client.authenticate()
    print("OAuth autenticato\n", flush=True)

    # Processa ogni job/run
    for job_number, run_number in JOB_RUN_MAP.items():
        print(f"=== Job #{job_number} → Run {run_number} ===", flush=True)

        artifacts = get_artifacts(job_number)
        if not artifacts:
            print(f"  ⚠ Nessun artifact trovato")
            continue

        process_run(client, run_number, artifacts)
        print(flush=True)
        time.sleep(2)  # Pausa tra run

    print("COMPLETATO!")

if __name__ == "__main__":
    main()
