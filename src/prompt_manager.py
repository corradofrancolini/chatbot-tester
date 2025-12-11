"""
Prompt Manager - Gestione versionata dei prompt

Funzionalita:
- Salvataggio prompt con versioning automatico
- Collegamento prompt a progetto
- Recupero prompt corrente/specifico
- Lista versioni disponibili
- Diff tra versioni

Struttura:
    projects/{project}/prompts/
        v001_2025-12-06_initial.md
        v002_2025-12-07_fix-greeting.md
        current -> v002_2025-12-07_fix-greeting.md (symlink)
        metadata.json

Usage:
    manager = PromptManager(project_name)
    manager.save("contenuto prompt", note="fix greeting")
    current = manager.get_current()
    versions = manager.list_versions()
"""

import os
import json
import hashlib
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any


@dataclass
class PromptVersion:
    """Rappresenta una versione di un prompt."""
    version: int
    date: str
    note: str
    filename: str
    hash: str
    tag: str = ""  # Tag human-readable (es. "fix-priority")
    parent_version: Optional[int] = None  # Versione da cui deriva
    source: str = "manual"  # Fonte: manual, diagnostic, import, test-run
    test_run: Optional[str] = None  # Run associato (es. "run_015")

    @property
    def version_id(self) -> str:
        """ID versione: v{NNN}_{tag}."""
        if self.tag:
            return f"v{self.version:03d}_{self.tag}"
        return f"v{self.version:03d}"

    @property
    def display_name(self) -> str:
        """Nome visualizzabile."""
        parts = [f"v{self.version:03d}"]
        if self.tag:
            parts.append(f"[{self.tag}]")
        parts.append(f"({self.date})")
        if self.note:
            parts.append(f"- {self.note}")
        return " ".join(parts)


@dataclass
class PromptMetadata:
    """Metadati del prompt manager per un progetto."""
    project: str
    current_version: Optional[int] = None
    versions: List[Dict[str, Any]] = field(default_factory=list)
    created: str = field(default_factory=lambda: datetime.now().isoformat())
    updated: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PromptMetadata':
        return cls(**data)


class PromptManager:
    """
    Gestisce i prompt di un progetto con versioning.

    Usage:
        manager = PromptManager("my-chatbot")

        # Salva nuovo prompt
        manager.save("Sei un assistente...", note="versione iniziale")

        # Recupera prompt corrente
        prompt = manager.get_current()

        # Lista versioni
        for v in manager.list_versions():
            print(v.display_name)

        # Recupera versione specifica
        prompt_v1 = manager.get_version(1)

        # Diff tra versioni
        diff = manager.diff(1, 2)
    """

    def __init__(self, project_name: str, base_dir: Optional[Path] = None):
        """
        Inizializza il manager per un progetto.

        Args:
            project_name: Nome del progetto
            base_dir: Directory base (default: chatbot-tester root)
        """
        self.project_name = project_name

        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            self.base_dir = Path(__file__).parent.parent

        self.prompts_dir = self.base_dir / "projects" / project_name / "prompts"
        self.metadata_file = self.prompts_dir / "metadata.json"

        # Crea directory se non esiste
        self.prompts_dir.mkdir(parents=True, exist_ok=True)

        # Carica o crea metadata
        self.metadata = self._load_metadata()

    def _load_metadata(self) -> PromptMetadata:
        """Carica metadata da file o crea nuovo."""
        if self.metadata_file.exists():
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return PromptMetadata.from_dict(data)
        return PromptMetadata(project=self.project_name)

    def _save_metadata(self) -> None:
        """Salva metadata su file."""
        self.metadata.updated = datetime.now().isoformat()
        with open(self.metadata_file, 'w', encoding='utf-8') as f:
            json.dump(self.metadata.to_dict(), f, indent=2, ensure_ascii=False)

    def _compute_hash(self, content: str) -> str:
        """Calcola hash del contenuto."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()[:12]

    def _get_next_version(self) -> int:
        """Ritorna il prossimo numero di versione."""
        if not self.metadata.versions:
            return 1
        return max(v['version'] for v in self.metadata.versions) + 1

    def save(
        self,
        content: str,
        note: str = "update",
        tag: str = "",
        parent_version: Optional[int] = None,
        source: str = "manual",
        test_run: Optional[str] = None,
        confirm_callback: Optional[callable] = None
    ) -> Optional[PromptVersion]:
        """
        Salva una nuova versione del prompt.

        Args:
            content: Contenuto del prompt
            note: Nota descrittiva della modifica
            tag: Tag human-readable (es. "fix-priority")
            parent_version: Versione da cui deriva
            source: Fonte della modifica (manual, diagnostic, import, test-run)
            test_run: Run di test associato (es. "run_015")
            confirm_callback: Callback per conferma utente (opzionale)

        Returns:
            PromptVersion creata o None se utente annulla
        """
        # Verifica se il contenuto e' cambiato
        content_hash = self._compute_hash(content)
        if self.metadata.versions:
            last_version = self.metadata.versions[-1]
            if last_version['hash'] == content_hash:
                # Contenuto identico, non creare nuova versione
                return PromptVersion(**last_version)

        # Crea nuova versione
        version_num = self._get_next_version()
        date_str = datetime.now().strftime('%Y-%m-%d')

        # Determina parent version se non specificato
        if parent_version is None and self.metadata.current_version:
            parent_version = self.metadata.current_version

        # Sanitizza tag per filename (es. "fix-priority" -> "fix-priority")
        safe_tag = "".join(c if c.isalnum() or c == '-' else '-' for c in tag.lower())
        safe_tag = safe_tag[:20].strip('-')  # Limita lunghezza

        # Genera filename: v{NNN}_{tag}.md o v{NNN}_{date}_{note}.md se no tag
        if safe_tag:
            filename = f"v{version_num:03d}_{safe_tag}.md"
        else:
            safe_note = "".join(c if c.isalnum() or c in '-_' else '-' for c in note.lower())
            safe_note = safe_note[:20]
            filename = f"v{version_num:03d}_{date_str}_{safe_note}.md"

        # Prepara version_data
        version_data = {
            'version': version_num,
            'date': date_str,
            'note': note,
            'filename': filename,
            'hash': content_hash,
            'tag': tag,
            'parent_version': parent_version,
            'source': source,
            'test_run': test_run
        }

        # Chiedi conferma se callback fornito
        if confirm_callback:
            version_preview = PromptVersion(**version_data)
            if not confirm_callback(version_preview, content):
                return None  # Utente ha annullato

        filepath = self.prompts_dir / filename

        # Scrivi file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        # Aggiorna metadata
        self.metadata.versions.append(version_data)
        self.metadata.current_version = version_num
        self._save_metadata()

        # Aggiorna symlink 'current'
        self._update_current_link(filename)

        return PromptVersion(**version_data)

    def save_with_confirmation(
        self,
        content: str,
        note: str,
        tag: str = "",
        source: str = "manual",
        test_run: Optional[str] = None,
        ui: Optional[Any] = None
    ) -> Optional[PromptVersion]:
        """
        Salva con conferma interattiva.

        Args:
            content: Contenuto del prompt
            note: Nota descrittiva
            tag: Tag (es. "fix-priority")
            source: Fonte della modifica
            test_run: Run associato
            ui: UI per interazione (da src.ui)

        Returns:
            PromptVersion o None se annullato
        """
        if ui is None:
            # No UI, salva direttamente
            return self.save(content, note=note, tag=tag, source=source, test_run=test_run)

        # Mostra anteprima
        version_num = self._get_next_version()
        version_id = f"v{version_num:03d}_{tag}" if tag else f"v{version_num:03d}"

        ui.section("Salvare nuova versione?")
        ui.print(f"  Version: {version_id}")
        ui.print(f"  Note: {note}")
        if tag:
            ui.print(f"  Tag: {tag}")
        ui.print(f"  Source: {source}")
        if test_run:
            ui.print(f"  Test Run: {test_run}")
        ui.print(f"  Content: {len(content)} chars")
        ui.print("")

        # Mostra diff se esiste versione precedente
        if self.metadata.current_version:
            current_content = self.get_current()
            if current_content:
                import difflib
                diff_lines = list(difflib.unified_diff(
                    current_content.splitlines()[:10],
                    content.splitlines()[:10],
                    lineterm='',
                    n=1
                ))
                if diff_lines:
                    ui.muted("  Diff (prime 10 righe):")
                    for line in diff_lines[:15]:
                        ui.print(f"  {line}")

        # Conferma
        if ui.confirm("Salvare?", default=True):
            return self.save(content, note=note, tag=tag, source=source, test_run=test_run)

        ui.warning("Salvataggio annullato")
        return None

    def _update_current_link(self, filename: str) -> None:
        """Aggiorna il symlink 'current' al file specificato."""
        current_link = self.prompts_dir / "current.md"

        # Rimuovi link esistente
        if current_link.exists() or current_link.is_symlink():
            current_link.unlink()

        # Crea nuovo link (relativo)
        current_link.symlink_to(filename)

    def get_current(self) -> Optional[str]:
        """
        Ritorna il contenuto del prompt corrente.

        Returns:
            Contenuto del prompt o None se non esiste
        """
        if not self.metadata.current_version:
            return None

        return self.get_version(self.metadata.current_version)

    def get_current_version(self) -> Optional[PromptVersion]:
        """
        Ritorna i metadati della versione corrente.

        Returns:
            PromptVersion o None se non esiste
        """
        if not self.metadata.current_version:
            return None

        for v in self.metadata.versions:
            if v['version'] == self.metadata.current_version:
                return PromptVersion(**v)
        return None

    def get_version(self, version: int) -> Optional[str]:
        """
        Ritorna il contenuto di una versione specifica.

        Args:
            version: Numero di versione

        Returns:
            Contenuto del prompt o None se non esiste
        """
        for v in self.metadata.versions:
            if v['version'] == version:
                filepath = self.prompts_dir / v['filename']
                if filepath.exists():
                    with open(filepath, 'r', encoding='utf-8') as f:
                        return f.read()
        return None

    def list_versions(self) -> List[PromptVersion]:
        """
        Lista tutte le versioni disponibili.

        Returns:
            Lista di PromptVersion ordinate per versione
        """
        versions = []
        for v in sorted(self.metadata.versions, key=lambda x: x['version']):
            # Compatibilità con versioni vecchie (senza nuovi campi)
            version_data = {
                'version': v['version'],
                'date': v['date'],
                'note': v['note'],
                'filename': v['filename'],
                'hash': v['hash'],
                'tag': v.get('tag', ''),
                'parent_version': v.get('parent_version'),
                'source': v.get('source', 'manual'),
                'test_run': v.get('test_run')
            }
            versions.append(PromptVersion(**version_data))
        return versions

    def get_by_tag(self, tag: str) -> Optional[PromptVersion]:
        """
        Trova una versione per tag.

        Args:
            tag: Tag da cercare (es. "fix-priority")

        Returns:
            PromptVersion o None se non trovata
        """
        for v in reversed(self.metadata.versions):
            if v.get('tag', '').lower() == tag.lower():
                return PromptVersion(**v)
        return None

    def get_by_version_id(self, version_id: str) -> Optional[PromptVersion]:
        """
        Trova versione per ID (es. "v003_fix-priority" o "v003").

        Args:
            version_id: ID versione

        Returns:
            PromptVersion o None
        """
        # Parse version_id
        if version_id.startswith('v'):
            parts = version_id[1:].split('_', 1)
            try:
                version_num = int(parts[0])
            except ValueError:
                return None

            # Cerca per numero versione
            for v in self.metadata.versions:
                if v['version'] == version_num:
                    return PromptVersion(**v)
        return None

    def get_version_chain(self, version: int) -> List[PromptVersion]:
        """
        Ritorna la catena di versioni parent.

        Args:
            version: Versione da cui partire

        Returns:
            Lista di versioni dalla più recente alla più vecchia
        """
        chain = []
        current = version

        while current is not None:
            for v in self.metadata.versions:
                if v['version'] == current:
                    chain.append(PromptVersion(**v))
                    current = v.get('parent_version')
                    break
            else:
                break

        return chain

    def diff(self, version_a: int, version_b: int) -> Optional[str]:
        """
        Genera diff tra due versioni.

        Args:
            version_a: Prima versione
            version_b: Seconda versione

        Returns:
            Diff in formato unified o None se errore
        """
        import difflib

        content_a = self.get_version(version_a)
        content_b = self.get_version(version_b)

        if content_a is None or content_b is None:
            return None

        lines_a = content_a.splitlines(keepends=True)
        lines_b = content_b.splitlines(keepends=True)

        diff = difflib.unified_diff(
            lines_a, lines_b,
            fromfile=f'v{version_a:03d}',
            tofile=f'v{version_b:03d}',
            lineterm=''
        )

        return ''.join(diff)

    def set_current(self, version: int) -> bool:
        """
        Imposta una versione specifica come corrente.

        Args:
            version: Numero di versione

        Returns:
            True se successo, False se versione non trovata
        """
        for v in self.metadata.versions:
            if v['version'] == version:
                self.metadata.current_version = version
                self._save_metadata()
                self._update_current_link(v['filename'])
                return True
        return False

    def import_prompt(self, filepath: Path, note: str = "imported") -> PromptVersion:
        """
        Importa un prompt da file esterno.

        Args:
            filepath: Path al file da importare
            note: Nota per la versione

        Returns:
            PromptVersion creata
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return self.save(content, note=note)

    def export_prompt(self, version: Optional[int] = None,
                      output_path: Optional[Path] = None) -> Optional[Path]:
        """
        Esporta un prompt su file esterno.

        Args:
            version: Versione da esportare (default: corrente)
            output_path: Path di output (default: genera nome)

        Returns:
            Path del file esportato o None se errore
        """
        if version is None:
            version = self.metadata.current_version

        if version is None:
            return None

        content = self.get_version(version)
        if content is None:
            return None

        if output_path is None:
            output_path = Path(f"prompt_{self.project_name}_v{version:03d}.md")

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return output_path

    def has_prompts(self) -> bool:
        """Verifica se ci sono prompt salvati."""
        return len(self.metadata.versions) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Functions
# ═══════════════════════════════════════════════════════════════════════════════

def prompt_manager_cli(project_name: str, action: str, **kwargs) -> None:
    """
    Interfaccia CLI per il prompt manager.

    Args:
        project_name: Nome progetto
        action: Azione (list, show, save, import, export, diff, set-current)
        **kwargs: Argomenti specifici per azione
    """
    from src.ui import get_ui
    ui = get_ui()

    manager = PromptManager(project_name)

    if action == 'list':
        versions = manager.list_versions()
        if not versions:
            ui.warning(f"Nessun prompt salvato per {project_name}")
            ui.muted("  Usa --prompt-import FILE per importare un prompt")
            return

        ui.section(f"Prompt versions - {project_name}")
        current = manager.metadata.current_version
        for v in versions:
            marker = " [current]" if v.version == current else ""
            # Formato: v{NNN}_{tag} o v{NNN}
            version_str = v.version_id
            # Aggiungi info su source e parent
            extras = []
            if v.source != "manual":
                extras.append(f"[{v.source}]")
            if v.parent_version:
                extras.append(f"< v{v.parent_version:03d}")
            if v.test_run:
                extras.append(f"@{v.test_run}")
            extra_str = " ".join(extras)
            ui.print(f"  {version_str:20}  {v.date}  {v.note}{marker}  {extra_str}")

    elif action == 'show':
        version = kwargs.get('version')
        if version:
            content = manager.get_version(version)
        else:
            content = manager.get_current()
            version = manager.metadata.current_version

        if content is None:
            ui.error("Prompt non trovato")
            return

        ui.section(f"Prompt v{version:03d}")
        ui.print(content)

    elif action == 'import':
        filepath = kwargs.get('filepath')
        note = kwargs.get('note', 'imported')

        if not filepath or not Path(filepath).exists():
            ui.error(f"File non trovato: {filepath}")
            return

        version = manager.import_prompt(Path(filepath), note=note)
        ui.success(f"Importato come {version.display_name}")

    elif action == 'export':
        version = kwargs.get('version')
        output = kwargs.get('output')

        result = manager.export_prompt(
            version=version,
            output_path=Path(output) if output else None
        )

        if result:
            ui.success(f"Esportato in {result}")
        else:
            ui.error("Errore durante l'export")

    elif action == 'diff':
        v1 = kwargs.get('version_a')
        v2 = kwargs.get('version_b')

        if v1 is None or v2 is None:
            ui.error("Specifica due versioni: --diff V1:V2")
            return

        diff = manager.diff(v1, v2)
        if diff:
            ui.section(f"Diff v{v1:03d} -> v{v2:03d}")
            ui.print(diff)
        else:
            ui.error("Impossibile generare diff")

    elif action == 'set-current':
        version = kwargs.get('version')
        if version is None:
            ui.error("Specifica una versione")
            return

        if manager.set_current(version):
            ui.success(f"Versione corrente: v{version:03d}")
        else:
            ui.error(f"Versione {version} non trovata")
