# STEP 7 — modules/recommender.py [CHECKPOINT]

**No hace requests.** Recibe el `ReconReport` parcial y produce `RecommenderResult`. Cada campo puede ser `None` — manejar sin excepción.

```python
def build_recommendation(report: ReconReport) -> RecommenderResult:
    """Pure function. No I/O. Returns RecommenderResult."""
```

La lógica completa del árbol de decisión (ramas 1–5, rama e-commerce por plataforma, y todos los flags adicionales) está en:

**→ [`docs/modules/recommender_logic.md`](../modules/recommender_logic.md)**

---

**[CHECKPOINT 7]** — Test unitario puro:
```bash
python -c "
from models.schemas import ReconReport, ModuleStatus
from modules.recommender import build_recommendation
from datetime import datetime

report = ReconReport(
    url='https://test.com',
    timestamp=datetime.now().isoformat(),
    scan_duration_ms=0,
    modules_status=[],
)
r = build_recommendation(report)
print(r.primary_library)
print(r.estimated_complexity)
"
```
