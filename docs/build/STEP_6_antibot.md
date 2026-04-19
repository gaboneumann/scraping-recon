# STEP 6 — modules/antibot.py [CHECKPOINT]

**Importa desde:** `utils.http`, `utils.tls_test`, `models.schemas.AntibotResult`

---

## Dimension 1: WAF

```python
# Primero: subprocess wafw00f
result = subprocess.run(
    ["wafw00f", url, "-o", "/tmp/wafw00f.json", "-f", "json"],
    capture_output=True, timeout=15
)
# Si falla: header detection como fallback

WAF_HEADER_SIGNALS = {
    "Cloudflare":  (3, ["CF-Ray", "__cf_bm"]),
    "DataDome":    (3, ["x-datadome"]),
    "PerimeterX":  (3, ["_px2", "pxCaptcha"]),
    "Akamai":      (3, ["x-akamai-transformed"]),
    "Kasada":      (3, ["x-kasada-info"]),
    "Imperva":     (2, ["incap_ses"]),
    "Sucuri":      (2, ["x-sucuri-id"]),
}
```

---

## Dimension 2: TLS

Delegar a `utils/tls_test.py`. Comparar `httpx` vs `curl_cffi chrome110` vs `curl_cffi safari17_0`. Métrica: `(status_code, len(body))` — si difiere entre clientes → TLS sensitivity detectada.

---

## Dimension 3: Rate Limiting

**⚠️ Delay mínimo entre requests: 0.3s. No reducir.**
```python
for i in range(8):
    status, _, _, _ = await make_request(url, ...)
    await asyncio.sleep(0.3)
    if status == 429: triggered_at = i; score = 3; break
    if status in (503, 520): score = 2; break
# Si response_time_ms último ≥ 3x primero: score=1
```

---

## Dimensions 4–7 (sobre HTML ya fetcheado — sin requests adicionales)

```python
CAPTCHA_SIGNALS = {
    "reCAPTCHA v2": (2, ["data-sitekey"]),
    "reCAPTCHA v3": (3, ["render="]),
    "hCaptcha":     (2, ["hcaptcha.com"]),
    "Turnstile":    (3, ["challenges.cloudflare.com/turnstile"]),
    "FunCaptcha":   (3, ["funcaptcha.com"]),
}

FINGERPRINT_SIGNALS = {
    "FingerprintJS":   (2, ["fpjs.io", "fingerprint.com"]),
    "Canvas FP":       (2, ["toDataURL", "getImageData"]),
    "AudioContext FP": (2, ["AudioContext", "AnalyserNode"]),
    "Webdriver check": (3, ["navigator.webdriver"]),
}

HONEYPOT_SELECTORS = [
    "[style*='display:none'] a",
    "[style*='visibility:hidden'] a",
    "[style*='left:-9999'] a",
    "[style*='left: -9999'] a",
]
```

---

## Score final

```python
score = sum([waf.score, tls.score, rate_limit.score, captcha.score,
             fingerprint.score, honeypot.score, ip_rep.score])
overall_score = round((score / 21) * 10, 2)

level = (
    "NONE"    if overall_score == 0   else
    "LOW"     if overall_score < 3    else
    "MEDIUM"  if overall_score < 5    else
    "HIGH"    if overall_score < 8    else
    "EXTREME"
)
```

---

**[CHECKPOINT 6]** — Ejecuta:
```bash
python -c "
import asyncio
from modules.antibot import analyze_antibot

async def test():
    r = await analyze_antibot('https://news.ycombinator.com', timeout=30)
    print(f'score={r.overall_score} level={r.overall_level}')
    for dim, val in r.dimensions.model_dump().items():
        print(f'  {dim}: {val[\"score\"]}')

asyncio.run(test())
"
```
Expected HN: score < 3, level=LOW o NONE.
