# STEP 5b — modules/auth_detector.py [CHECKPOINT]

**Importa desde:** `utils.http`, `models.schemas.AuthResult`

Reutiliza el HTML ya fetcheado por classifier — solo añade 1 request de probe si es necesario.

---

## Detección de login wall

```python
LOGIN_FORM_SELECTORS = [
    'input[type="password"]',
    'form[action*="login"]',
    'form[action*="signin"]',
    'form[action*="session"]',
]

LOGIN_LINK_SELECTORS = [
    'a[href*="/login"]',
    'a[href*="/signin"]',
    'a[href*="/auth"]',
    'a[href*="/account"]',
]

OAUTH_DOMAINS = [
    "accounts.google.com",
    "facebook.com/login",
    "twitter.com/oauth",
    "github.com/login/oauth",
    "login.microsoftonline.com",
    "appleid.apple.com",
]
```

- Si `input[type=password]` en DOM: `type="FORM"`, `login_url` = `form[action]`
- Si redirect chain pasa por un `OAUTH_DOMAIN`: `type="OAUTH"`
- Si response inicial es 401 con `WWW-Authenticate`: `type="API_KEY"`
- Si solo hay links de login (no form): `type="FORM"`, `required=True`
- Si ninguna señal: `required=False`, `type="NONE"`

---

## Detección de paywall

```python
PAYWALL_HARD_SIGNALS = [
    "subscribe to read", "subscribers only", "sign up to continue",
    "create an account to", "members only", "premium content",
]
PAYWALL_METERED_SIGNALS = [
    "articles remaining", "free articles left", "monthly limit",
    "you have read", "stories this month",
]
```

- Si señales HARD Y `<article>` o `<main>` tiene menos de 200 palabras visibles: `paywall_type="HARD"`
- Si señales METERED: `paywall_type="METERED"`
- Sino: `paywall_type="NONE"`

---

## Detección de cookie consent wall

```python
CONSENT_SIGNALS = {
    "OneTrust":  ["onetrust-banner-sdk", "onetrust-accept-btn-handler"],
    "Cookiebot": ["CybotCookiebotDialog"],
    "TrustArc":  ["truste-consent-track"],
    "Quantcast": ["qc-cmp2-ui"],
    "Generic":   ["cookie-consent", "cookie-banner", "gdpr-banner"],
}
```

`cookie_consent_blocking=True` si se detecta alguna señal Y el `<body>` tiene `overflow:hidden` o el banner tiene `position:fixed` con `z-index` alto (> 999).

---

**[CHECKPOINT 5b]** — Ejecuta:
```bash
python -c "
import asyncio
from modules.auth_detector import detect_auth

async def test():
    for url in ['https://example.com', 'https://quotes.toscrape.com']:
        r = await detect_auth(url, timeout=10)
        print(url.split('/')[2], r.required, r.type, r.cookie_consent_blocking)

asyncio.run(test())
"
```
Expected: ambos `required=False`, `type=NONE`, `cookie_consent_blocking=False`.
