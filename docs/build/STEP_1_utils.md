# STEP 1 — utils/ [CHECKPOINT]

Dos utilidades base. Implementar en orden: `graceful.py` primero, `http.py` segundo.

---

## 1a — utils/graceful.py

Runner genérico que envuelve cada módulo con timeout de 20s, captura de excepción sin propagación, y retorno de `ModuleStatus` estructurado.

```python
"""
utils/graceful.py
Wraps async module coroutines with timeout and structured error capture.
All modules are invoked through run_module() — never called directly.
"""
import asyncio
import traceback
from typing import Any, Callable, Coroutine
from models.schemas import ModuleStatus


async def run_module(
    name: str,
    coro: Coroutine[Any, Any, Any],
    timeout: float = 20.0,
) -> tuple[Any | None, ModuleStatus]:
    """
    Execute a module coroutine with timeout and exception capture.

    Returns:
        (result, ModuleStatus) — result is None on failure.
    """
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        return result, ModuleStatus(name=name, status="OK")
    except asyncio.TimeoutError:
        return None, ModuleStatus(
            name=name,
            status="INCOMPLETE",
            error=f"Timed out after {timeout}s",
        )
    except Exception:
        return None, ModuleStatus(
            name=name,
            status="INCOMPLETE",
            error=traceback.format_exc(limit=3),
        )
```

**[CHECKPOINT 1a]** — Ejecuta:
```bash
python -c "
import asyncio
from utils.graceful import run_module

async def test():
    async def ok(): return 42
    async def boom(): raise ValueError('test error')
    async def slow():
        await asyncio.sleep(99)

    r1, s1 = await run_module('ok', ok())
    r2, s2 = await run_module('boom', boom())
    r3, s3 = await run_module('slow', slow(), timeout=0.1)
    print(s1.status, r1)           # OK 42
    print(s2.status, s2.error[:30])  # INCOMPLETE ...
    print(s3.status, s3.error)     # INCOMPLETE Timed out...

asyncio.run(test())
"
```

---

## 1b — utils/http.py

HTTP client factory. Centraliza toda la lógica de requests. Sin estado global — cada llamada recibe config explícita.

**Funciones a implementar:**
1. `make_request(url, ua, timeout, verify_ssl, impersonate)` → `(status_code, headers, text, response_time_ms)`
2. `try_with_fallback_uas(url, config)` → prueba 3 UAs en secuencia, retorna el primero exitoso
3. `detect_block(status, text)` → `bool` — detecta 403/503 con body de WAF

**UAs:**
```python
UA_PYTHON    = "python-httpx/0.27"
UA_GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
UA_CHROME    = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
UA_MOBILE    = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
```

**Funciones adicionales:**
4. `compare_mobile_desktop(url, timeout)` → `dict` con `content_differs: bool, size_diff_pct: float`
   - Fetch con `UA_CHROME` y luego con `UA_MOBILE`
   - `size_diff_pct = abs(len(desktop) - len(mobile)) / max(len(desktop), 1)`
   - `content_differs=True` si `size_diff_pct > 0.15` o si los títulos `<h1>` difieren

**Reglas:**
- Timeout default: `config.timeout` (no hardcodear)
- Retry: 2 intentos con 1s backoff en `ConnectionError` y `TimeoutError`
- SSL error: retry con `verify=False` + loguea el warning
- Máximo 5MB de contenido (stream con límite)
- Seguir redirects hasta 10, loguear la cadena completa
- Si `curl_cffi` no está instalado: usar `httpx` solamente, setear `TLS_IMPERSONATION_AVAILABLE = False`

**[CHECKPOINT 1b]** — Ejecuta:
```bash
python -c "
import asyncio
from utils.http import make_request

async def test():
    status, headers, text, ms = await make_request('https://httpbin.org/get', timeout=10)
    print(f'status={status} time={ms}ms len={len(text)}')
    print('server:', headers.get('server', 'n/a'))

asyncio.run(test())
"
```
