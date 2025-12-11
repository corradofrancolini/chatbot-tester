"""
Fine-tuning Pipeline - Addestramento modello valutatore personalizzato

Gestisce:
- Export dati training in formato JSONL
- Validazione dataset
- Fine-tuning con Ollama (Modelfile) o OpenAI API
- Valutazione modello su test set

Usage:
    from src.finetuning import FineTuningPipeline

    pipeline = FineTuningPipeline(project_dir)

    # Export e valida
    jsonl_path = pipeline.export_training_data()
    stats = pipeline.validate_dataset(jsonl_path)

    # Fine-tune
    pipeline.finetune_ollama("llama3.2:3b", "chatbot-evaluator")
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DatasetStats:
    """Statistiche del dataset di training"""
    total_examples: int = 0
    pass_count: int = 0
    fail_count: int = 0
    skip_count: int = 0
    avg_question_length: int = 0
    avg_response_length: int = 0
    categories: Dict[str, int] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    is_valid: bool = False


@dataclass
class FineTuneConfig:
    """Configurazione per fine-tuning"""
    base_model: str = "llama3.2:3b"
    output_model: str = "chatbot-evaluator"
    system_prompt: str = ""
    temperature: float = 0.1
    num_epochs: int = 3
    learning_rate: float = 1e-5


class FineTuningPipeline:
    """
    Pipeline completa per fine-tuning di un modello valutatore.

    Supporta:
    - Ollama (locale, gratuito)
    - OpenAI (API, a pagamento)
    """

    SYSTEM_PROMPT_TEMPLATE = """Sei un valutatore esperto di risposte chatbot.
Il tuo compito è valutare se la risposta del chatbot è corretta e appropriata.

Criteri di valutazione:
- PASS: Risposta corretta, completa e pertinente alla domanda
- FAIL: Risposta errata, incompleta, fuori tema o con informazioni sbagliate
- SKIP: Impossibile valutare (domanda ambigua, contesto mancante)

Rispondi SOLO con: PASS, FAIL o SKIP seguito da una breve spiegazione (max 50 parole).

Formato risposta:
PASS|FAIL|SKIP - [spiegazione breve]"""

    def __init__(self, project_dir: Path):
        """
        Inizializza la pipeline.

        Args:
            project_dir: Directory del progetto
        """
        self.project_dir = Path(project_dir)
        self.training_file = self.project_dir / "training_data.json"
        self.finetuning_dir = self.project_dir / "finetuning"
        self.finetuning_dir.mkdir(exist_ok=True)

    def load_training_data(self) -> Dict[str, Any]:
        """Carica dati di training esistenti"""
        if not self.training_file.exists():
            return {"patterns": [], "examples": []}

        with open(self.training_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def export_training_data(self,
                             output_format: str = "jsonl",
                             include_notes: bool = True) -> Path:
        """
        Esporta dati training in formato per fine-tuning.

        Args:
            output_format: "jsonl" (OpenAI/standard) o "ollama" (Modelfile)
            include_notes: Se includere le note come parte della spiegazione

        Returns:
            Path al file esportato
        """
        data = self.load_training_data()
        examples = data.get("examples", [])

        if not examples:
            raise ValueError("Nessun esempio di training trovato")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if output_format == "jsonl":
            return self._export_jsonl(examples, include_notes, timestamp)
        elif output_format == "ollama":
            return self._export_ollama_modelfile(examples, include_notes, timestamp)
        else:
            raise ValueError(f"Formato non supportato: {output_format}")

    def _export_jsonl(self,
                      examples: List[Dict],
                      include_notes: bool,
                      timestamp: str) -> Path:
        """Esporta in formato JSONL (OpenAI fine-tuning format)"""
        output_path = self.finetuning_dir / f"training_{timestamp}.jsonl"

        with open(output_path, 'w', encoding='utf-8') as f:
            for ex in examples:
                if not ex.get("question") or not ex.get("response"):
                    continue

                esito = ex.get("esito", "").upper()
                if esito not in ["PASS", "FAIL", "SKIP"]:
                    continue

                # Costruisci messaggio utente
                user_msg = f"""Valuta questa risposta del chatbot:

DOMANDA: {ex['question']}

RISPOSTA: {ex['response']}

La risposta è corretta?"""

                # Costruisci risposta attesa
                notes = ex.get("notes", "")
                if include_notes and notes:
                    assistant_msg = f"{esito} - {notes[:100]}"
                else:
                    assistant_msg = esito

                # Formato OpenAI chat completions
                record = {
                    "messages": [
                        {"role": "system", "content": self.SYSTEM_PROMPT_TEMPLATE},
                        {"role": "user", "content": user_msg},
                        {"role": "assistant", "content": assistant_msg}
                    ]
                }

                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return output_path

    def _export_ollama_modelfile(self,
                                  examples: List[Dict],
                                  include_notes: bool,
                                  timestamp: str) -> Path:
        """Esporta come Ollama Modelfile con esempi embedded"""
        output_path = self.finetuning_dir / f"Modelfile_{timestamp}"

        # Costruisci esempi per il prompt
        examples_text = []
        for i, ex in enumerate(examples[:50], 1):  # Max 50 esempi nel Modelfile
            if not ex.get("question") or not ex.get("response"):
                continue

            esito = ex.get("esito", "").upper()
            if esito not in ["PASS", "FAIL", "SKIP"]:
                continue

            notes = ex.get("notes", "")
            explanation = f" - {notes[:50]}" if include_notes and notes else ""

            examples_text.append(f"""Esempio {i}:
Q: {ex['question'][:200]}
A: {ex['response'][:300]}
Valutazione: {esito}{explanation}
""")

        # Genera Modelfile
        modelfile_content = f'''FROM llama3.2:3b

SYSTEM """
{self.SYSTEM_PROMPT_TEMPLATE}

ESEMPI DI VALUTAZIONE:

{chr(10).join(examples_text)}
"""

PARAMETER temperature 0.1
PARAMETER top_p 0.9
'''

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(modelfile_content)

        return output_path

    def validate_dataset(self, jsonl_path: Optional[Path] = None) -> DatasetStats:
        """
        Valida qualità e quantità del dataset.

        Args:
            jsonl_path: Path al file JSONL (se None, valida training_data.json)

        Returns:
            DatasetStats con statistiche e problemi rilevati
        """
        stats = DatasetStats()

        if jsonl_path:
            # Valida file JSONL
            examples = []
            with open(jsonl_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        messages = record.get("messages", [])

                        # Estrai info
                        user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
                        assistant_msg = next((m["content"] for m in messages if m["role"] == "assistant"), "")

                        examples.append({
                            "question": user_msg,
                            "response": "",
                            "esito": assistant_msg.split()[0] if assistant_msg else ""
                        })
                    except:
                        stats.issues.append(f"Riga JSON non valida")
        else:
            # Valida training_data.json
            data = self.load_training_data()
            examples = data.get("examples", [])

        if not examples:
            stats.issues.append("Dataset vuoto")
            return stats

        # Calcola statistiche
        stats.total_examples = len(examples)

        question_lengths = []
        response_lengths = []

        for ex in examples:
            esito = ex.get("esito", "").upper()

            if esito == "PASS":
                stats.pass_count += 1
            elif esito == "FAIL":
                stats.fail_count += 1
            elif esito == "SKIP":
                stats.skip_count += 1

            # Categoria
            category = ex.get("category", "uncategorized")
            stats.categories[category] = stats.categories.get(category, 0) + 1

            # Lunghezze
            q_len = len(ex.get("question", ""))
            r_len = len(ex.get("response", ""))
            if q_len > 0:
                question_lengths.append(q_len)
            if r_len > 0:
                response_lengths.append(r_len)

        if question_lengths:
            stats.avg_question_length = sum(question_lengths) // len(question_lengths)
        if response_lengths:
            stats.avg_response_length = sum(response_lengths) // len(response_lengths)

        # Validazione qualità
        if stats.total_examples < 50:
            stats.issues.append(f"Dataset troppo piccolo ({stats.total_examples} esempi, minimo 50)")

        if stats.total_examples < 100:
            stats.issues.append(f"Dataset sotto la soglia consigliata (100+ esempi)")

        # Bilanciamento
        if stats.pass_count > 0 and stats.fail_count > 0:
            ratio = stats.pass_count / stats.fail_count
            if ratio > 3 or ratio < 0.33:
                stats.issues.append(f"Dataset sbilanciato: {stats.pass_count} PASS vs {stats.fail_count} FAIL")
        elif stats.fail_count == 0:
            stats.issues.append("Nessun esempio FAIL - il modello non imparerà a riconoscere errori")
        elif stats.pass_count == 0:
            stats.issues.append("Nessun esempio PASS - il modello non imparerà a riconoscere risposte corrette")

        # Determina validità
        stats.is_valid = (
            stats.total_examples >= 50 and
            stats.pass_count >= 10 and
            stats.fail_count >= 10
        )

        return stats

    def finetune_ollama(self,
                        base_model: str = "llama3.2:3b",
                        output_model: str = "chatbot-evaluator",
                        modelfile_path: Optional[Path] = None) -> Tuple[bool, str]:
        """
        Crea modello fine-tuned con Ollama.

        Nota: Ollama non supporta vero fine-tuning, ma crea un modello
        con system prompt e esempi embedded.

        Args:
            base_model: Modello base Ollama
            output_model: Nome modello output
            modelfile_path: Path al Modelfile (se None, lo genera)

        Returns:
            (success, message)
        """
        # Verifica Ollama installato
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                return False, "Ollama non raggiungibile"
        except FileNotFoundError:
            return False, "Ollama non installato. Installa da https://ollama.ai"
        except subprocess.TimeoutExpired:
            return False, "Timeout connessione Ollama"

        # Genera Modelfile se non fornito
        if not modelfile_path:
            modelfile_path = self.export_training_data(output_format="ollama")

        # Modifica FROM nel Modelfile
        with open(modelfile_path, 'r', encoding='utf-8') as f:
            content = f.read()

        content = content.replace("FROM llama3.2:3b", f"FROM {base_model}")

        with open(modelfile_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # Crea modello
        try:
            result = subprocess.run(
                ["ollama", "create", output_model, "-f", str(modelfile_path)],
                capture_output=True,
                text=True,
                timeout=300  # 5 minuti
            )

            if result.returncode == 0:
                return True, f"Modello '{output_model}' creato con successo"
            else:
                return False, f"Errore creazione: {result.stderr}"

        except subprocess.TimeoutExpired:
            return False, "Timeout durante creazione modello"
        except Exception as e:
            return False, f"Errore: {e}"

    def finetune_openai(self,
                        api_key: str,
                        jsonl_path: Path,
                        base_model: str = "gpt-4o-mini-2024-07-18",
                        suffix: str = "chatbot-evaluator") -> Tuple[bool, str]:
        """
        Lancia fine-tuning su OpenAI.

        Args:
            api_key: OpenAI API key
            jsonl_path: Path al file JSONL di training
            base_model: Modello base (gpt-4o-mini, gpt-3.5-turbo)
            suffix: Suffisso per il modello fine-tuned

        Returns:
            (success, message/job_id)
        """
        try:
            import openai
        except ImportError:
            return False, "Installa openai: pip install openai"

        client = openai.OpenAI(api_key=api_key)

        try:
            # Upload file
            with open(jsonl_path, 'rb') as f:
                file_response = client.files.create(
                    file=f,
                    purpose="fine-tune"
                )

            file_id = file_response.id

            # Crea job
            job = client.fine_tuning.jobs.create(
                training_file=file_id,
                model=base_model,
                suffix=suffix
            )

            return True, f"Job creato: {job.id}"

        except Exception as e:
            return False, f"Errore OpenAI: {e}"

    def check_openai_job(self, api_key: str, job_id: str) -> Dict[str, Any]:
        """Controlla stato job OpenAI fine-tuning"""
        try:
            import openai
            client = openai.OpenAI(api_key=api_key)

            job = client.fine_tuning.jobs.retrieve(job_id)

            return {
                "status": job.status,
                "model": job.fine_tuned_model,
                "created_at": job.created_at,
                "finished_at": job.finished_at,
                "error": job.error
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def evaluate_model(self,
                       model: str,
                       test_examples: List[Dict],
                       provider: str = "ollama") -> Dict[str, Any]:
        """
        Valuta accuracy del modello su un test set.

        Args:
            model: Nome modello da testare
            test_examples: Lista esempi con ground truth
            provider: "ollama" o "openai"

        Returns:
            Metriche di valutazione
        """
        results = {
            "total": len(test_examples),
            "correct": 0,
            "incorrect": 0,
            "confusion_matrix": {
                "PASS": {"PASS": 0, "FAIL": 0, "SKIP": 0},
                "FAIL": {"PASS": 0, "FAIL": 0, "SKIP": 0},
                "SKIP": {"PASS": 0, "FAIL": 0, "SKIP": 0}
            },
            "predictions": []
        }

        for ex in test_examples:
            ground_truth = ex.get("esito", "").upper()
            if ground_truth not in ["PASS", "FAIL", "SKIP"]:
                continue

            # Genera predizione
            prompt = f"""Valuta questa risposta del chatbot:

DOMANDA: {ex['question']}

RISPOSTA: {ex['response']}

La risposta è corretta?"""

            prediction = self._get_prediction(model, prompt, provider)

            # Estrai verdetto
            pred_verdict = "SKIP"
            for v in ["PASS", "FAIL", "SKIP"]:
                if v in prediction.upper():
                    pred_verdict = v
                    break

            # Aggiorna metriche
            if pred_verdict == ground_truth:
                results["correct"] += 1
            else:
                results["incorrect"] += 1

            results["confusion_matrix"][ground_truth][pred_verdict] += 1
            results["predictions"].append({
                "question": ex["question"][:50],
                "ground_truth": ground_truth,
                "prediction": pred_verdict,
                "correct": pred_verdict == ground_truth
            })

        # Calcola accuracy
        if results["total"] > 0:
            results["accuracy"] = results["correct"] / results["total"]
        else:
            results["accuracy"] = 0

        # Precision/Recall per FAIL (il più importante)
        fail_tp = results["confusion_matrix"]["FAIL"]["FAIL"]
        fail_fp = results["confusion_matrix"]["PASS"]["FAIL"] + results["confusion_matrix"]["SKIP"]["FAIL"]
        fail_fn = results["confusion_matrix"]["FAIL"]["PASS"] + results["confusion_matrix"]["FAIL"]["SKIP"]

        results["fail_precision"] = fail_tp / (fail_tp + fail_fp) if (fail_tp + fail_fp) > 0 else 0
        results["fail_recall"] = fail_tp / (fail_tp + fail_fn) if (fail_tp + fail_fn) > 0 else 0

        return results

    def _get_prediction(self, model: str, prompt: str, provider: str) -> str:
        """Ottiene predizione dal modello"""
        if provider == "ollama":
            try:
                import requests
                response = requests.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False
                    },
                    timeout=30
                )
                if response.status_code == 200:
                    return response.json().get("response", "SKIP")
            except:
                pass
            return "SKIP - Error"

        elif provider == "openai":
            try:
                import openai
                client = openai.OpenAI()
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": self.SYSTEM_PROMPT_TEMPLATE},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=100
                )
                return response.choices[0].message.content
            except:
                pass
            return "SKIP - Error"

        return "SKIP - Unknown provider"

    def split_dataset(self,
                      test_ratio: float = 0.2,
                      seed: int = 42) -> Tuple[List[Dict], List[Dict]]:
        """
        Divide dataset in training e test set.

        Args:
            test_ratio: Percentuale per test set
            seed: Seed per riproducibilità

        Returns:
            (train_examples, test_examples)
        """
        import random

        data = self.load_training_data()
        examples = data.get("examples", [])

        random.seed(seed)
        random.shuffle(examples)

        split_idx = int(len(examples) * (1 - test_ratio))

        return examples[:split_idx], examples[split_idx:]

    def get_available_models(self) -> Dict[str, List[str]]:
        """Restituisce modelli disponibili per fine-tuning"""
        models = {
            "ollama": [],
            "openai": [
                "gpt-4o-mini-2024-07-18",
                "gpt-3.5-turbo-0125"
            ]
        }

        # Check Ollama models
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")[1:]  # Skip header
                for line in lines:
                    if line.strip():
                        model_name = line.split()[0]
                        models["ollama"].append(model_name)
        except:
            pass

        return models
