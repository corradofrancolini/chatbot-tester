"""
Report Cleanup - Automatic cleanup of old test reports

Features:
- Delete reports older than N days
- Compress old reports instead of deleting
- Keep only last N runs
- Interactive or automatic mode
- Configurable per project or global
"""

import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass
import json


@dataclass
class CleanupConfig:
    """Configurazione pulizia report"""
    enabled: bool = False
    auto_cleanup: bool = False  # Se False, chiede conferma
    max_age_days: int = 30
    keep_last_n: int = 50
    compress_instead_delete: bool = False
    keep_screenshots: bool = True  # Mantieni screenshot anche se cancelli report


@dataclass
class CleanupResult:
    """Risultato operazione cleanup"""
    runs_deleted: List[str]
    runs_compressed: List[str]
    space_freed_mb: float
    space_freed_human: str


class ReportCleanup:
    """Gestisce pulizia automatica dei report"""

    def __init__(self, config: CleanupConfig, reports_dir: Path):
        self.config = config
        self.reports_dir = reports_dir

    def get_old_runs(self, project: str) -> List[Dict]:
        """
        Trova RUN più vecchie di max_age_days.

        Returns:
            Lista di dict con info su ogni RUN vecchia:
            {
                'path': Path,
                'run_number': int,
                'age_days': int,
                'size_mb': float,
                'created': datetime
            }
        """
        project_dir = self.reports_dir / project
        if not project_dir.exists():
            return []

        old_runs = []
        cutoff_date = datetime.now() - timedelta(days=self.config.max_age_days)

        for run_dir in sorted(project_dir.glob("run_*")):
            if not run_dir.is_dir():
                continue

            # Estrai numero RUN
            try:
                run_num = int(run_dir.name.split("_")[1])
            except (ValueError, IndexError):
                continue

            # Data creazione directory
            created = datetime.fromtimestamp(run_dir.stat().st_mtime)

            # Se più vecchia di cutoff_date
            if created < cutoff_date:
                age_days = (datetime.now() - created).days
                size_mb = self._get_dir_size_mb(run_dir)

                old_runs.append({
                    'path': run_dir,
                    'run_number': run_num,
                    'age_days': age_days,
                    'size_mb': size_mb,
                    'created': created
                })

        return old_runs

    def get_excess_runs(self, project: str) -> List[Dict]:
        """
        Trova RUN in eccesso rispetto a keep_last_n.

        Mantiene le ultime N RUN, restituisce quelle più vecchie.
        """
        project_dir = self.reports_dir / project
        if not project_dir.exists():
            return []

        all_runs = []
        for run_dir in project_dir.glob("run_*"):
            if not run_dir.is_dir():
                continue

            try:
                run_num = int(run_dir.name.split("_")[1])
            except (ValueError, IndexError):
                continue

            created = datetime.fromtimestamp(run_dir.stat().st_mtime)
            size_mb = self._get_dir_size_mb(run_dir)

            all_runs.append({
                'path': run_dir,
                'run_number': run_num,
                'age_days': (datetime.now() - created).days,
                'size_mb': size_mb,
                'created': created
            })

        # Ordina per numero RUN (decrescente)
        all_runs.sort(key=lambda x: x['run_number'], reverse=True)

        # Restituisci quelle in eccesso
        if len(all_runs) > self.config.keep_last_n:
            return all_runs[self.config.keep_last_n:]

        return []

    def cleanup(self, project: str, dry_run: bool = False) -> CleanupResult:
        """
        Esegue cleanup per un progetto.

        Args:
            project: Nome progetto
            dry_run: Se True, simula senza cancellare

        Returns:
            Risultato cleanup con statistiche
        """
        # Trova RUN da pulire
        old_runs = self.get_old_runs(project)
        excess_runs = self.get_excess_runs(project)

        # Unisci evitando duplicati
        runs_to_clean = {run['path']: run for run in old_runs + excess_runs}
        runs_to_clean = list(runs_to_clean.values())

        if not runs_to_clean:
            return CleanupResult([], [], 0.0, "0 B")

        deleted = []
        compressed = []
        space_freed = 0.0

        for run_info in runs_to_clean:
            run_path = run_info['path']
            size_mb = run_info['size_mb']

            if dry_run:
                # Simula
                if self.config.compress_instead_delete:
                    compressed.append(run_path.name)
                else:
                    deleted.append(run_path.name)
                space_freed += size_mb
            else:
                # Esegui realmente
                if self.config.compress_instead_delete:
                    # Comprimi
                    archive_path = self._compress_run(run_path)
                    if archive_path:
                        compressed.append(run_path.name)
                        # Calcola spazio risparmiato
                        compressed_size = archive_path.stat().st_size / (1024 * 1024)
                        space_freed += (size_mb - compressed_size)
                else:
                    # Cancella
                    if self._delete_run(run_path):
                        deleted.append(run_path.name)
                        space_freed += size_mb

        # Formato human-readable
        space_human = self._format_size(space_freed * 1024 * 1024)

        return CleanupResult(deleted, compressed, space_freed, space_human)

    def _compress_run(self, run_path: Path) -> Optional[Path]:
        """Comprimi una RUN in archivio .tar.gz"""
        try:
            archive_name = run_path.parent / f"{run_path.name}.tar.gz"
            shutil.make_archive(
                str(run_path.parent / run_path.name),
                'gztar',
                run_path
            )

            # Cancella directory originale
            shutil.rmtree(run_path)

            return archive_name
        except Exception:
            return None

    def _delete_run(self, run_path: Path) -> bool:
        """Cancella una RUN"""
        try:
            shutil.rmtree(run_path)
            return True
        except Exception:
            return False

    def _get_dir_size_mb(self, path: Path) -> float:
        """Calcola dimensione directory in MB"""
        total = 0
        try:
            for item in path.rglob("*"):
                if item.is_file():
                    total += item.stat().st_size
        except Exception:
            pass
        return total / (1024 * 1024)

    def _format_size(self, size_bytes: float) -> str:
        """Formatta dimensione in formato human-readable"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    def should_run_cleanup(self, project: str) -> bool:
        """
        Verifica se è il momento di eseguire cleanup.

        Controlla file .last_cleanup per vedere quando è stato eseguito
        l'ultimo cleanup.
        """
        if not self.config.enabled:
            return False

        project_dir = self.reports_dir / project
        if not project_dir.exists():
            return False

        last_cleanup_file = project_dir / ".last_cleanup"

        if not last_cleanup_file.exists():
            # Mai eseguito cleanup
            return True

        try:
            last_cleanup = datetime.fromisoformat(
                last_cleanup_file.read_text().strip()
            )
            days_since = (datetime.now() - last_cleanup).days

            # Esegui cleanup ogni max_age_days
            return days_since >= self.config.max_age_days
        except Exception:
            return True

    def mark_cleanup_done(self, project: str):
        """Segna che cleanup è stato eseguito"""
        project_dir = self.reports_dir / project
        if not project_dir.exists():
            return

        last_cleanup_file = project_dir / ".last_cleanup"
        last_cleanup_file.write_text(datetime.now().isoformat())


def cleanup_interactive(project: str, reports_dir: Path, config: CleanupConfig):
    """
    Cleanup interattivo con richiesta conferma.

    Mostra RUN da cancellare e chiede conferma all'utente.
    """
    cleanup = ReportCleanup(config, reports_dir)

    # Simula cleanup
    result = cleanup.cleanup(project, dry_run=True)

    if not result.runs_deleted and not result.runs_compressed:
        print(f"✓ Nessuna RUN da pulire per {project}")
        return

    # Mostra cosa verrà fatto
    print(f"\n🧹 CLEANUP - {project}")
    print("=" * 50)

    if result.runs_deleted:
        print(f"\n📁 RUN da cancellare ({len(result.runs_deleted)}):")
        for run_name in result.runs_deleted[:5]:
            print(f"  - {run_name}")
        if len(result.runs_deleted) > 5:
            print(f"  ... e altre {len(result.runs_deleted) - 5}")

    if result.runs_compressed:
        print(f"\n📦 RUN da comprimere ({len(result.runs_compressed)}):")
        for run_name in result.runs_compressed[:5]:
            print(f"  - {run_name}")
        if len(result.runs_compressed) > 5:
            print(f"  ... e altre {len(result.runs_compressed) - 5}")

    print(f"\n💾 Spazio liberato: {result.space_freed_human}")
    print("=" * 50)

    # Chiedi conferma
    response = input("\nProcedere? [s/N]: ").strip().lower()

    if response in ('s', 'si', 'sì', 'y', 'yes'):
        print("\n⏳ Cleanup in corso...")
        result = cleanup.cleanup(project, dry_run=False)
        print(f"✓ Cleanup completato!")
        print(f"  - Cancellate: {len(result.runs_deleted)} RUN")
        print(f"  - Compresse: {len(result.runs_compressed)} RUN")
        print(f"  - Spazio liberato: {result.space_freed_human}")
        cleanup.mark_cleanup_done(project)
    else:
        print("Cleanup annullato")
