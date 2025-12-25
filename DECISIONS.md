# Decision Log

Cronologia delle decisioni architetturali e di design.

---

## 2024-12-24: Refactoring APOSD

**Contesto**: Analisi codebase con principi "A Philosophy of Software Design" per ridurre complessità e migliorare manutenibilità.

**Problemi identificati**:
- TestExecutor aveva 13 parametri nel costruttore
- `_execute_train_test()` era 200+ righe
- Duplicazione tra `TestExecutor.persist()` e `ChatbotTester._save_result()`

**Decisioni**:

| Decisione | Alternativa scartata | Motivazione |
|-----------|---------------------|-------------|
| ExecutionContext dataclass | Oggetti separati (Services, Config, Output) | Semplicità, meno indirezione |
| TestMode enum | Stringa | Type safety, suggerimento Antigravity |
| `_save_result` delega a executor | Mantenere duplicazione | DRY, deep module pattern |
| RequestError ON HOLD | Implementare subito | Troppo invasivo, paradigm shift |

**Implementazione**:
- `src/models/execution.py`: ExecutionContext + TestMode enum
- `src/models/sheet_schema.py`: Schema colonne estratto
- `src/engine/executor.py`: Costruttore 13→1 param, aggiunto `persist()`
- `src/tester.py`: Split `_execute_train_test()` in 4 metodi, `_save_result()` ridotto a 3 righe

**Revisore**: Antigravity

---

## Template per nuove decisioni

```markdown
## YYYY-MM-DD: Titolo

**Contesto**: Perché questa decisione era necessaria

**Opzioni considerate**:
1. Opzione A - pro/contro
2. Opzione B - pro/contro

**Decisione**: Quale opzione e perché

**Conseguenze**: Cosa cambia, eventuali trade-off
```
