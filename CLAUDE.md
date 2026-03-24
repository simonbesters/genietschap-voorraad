# Genietschap Voorraad — Project Handover

## Workflow Orchestration

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately – don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop
- After ANY correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes – don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Write a test to reproduce the bug first
- Point at logs, errors, failing tests – then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management

1. **Plan First**: Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/todo.md`
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
- **NEVER COMMIT**: You will never commit to this repository. No PR's, nothing. Keep everything in the user's hands and locally.



## Wat is dit?
Een mobile-first Flask webapp (PWA) voor een stichting die champagne importeert. De 6 leden kunnen hiermee:
- De actuele keldervoorraad bekijken (live uit WooCommerce)
- Flessen meenemen registreren via een mandje-flow (meerdere flessen per sessie)
- Leveringen registreren (admin-only)
- Een logboek inzien van alle afnames per sessie

## Architectuur
**WooCommerce is de single source of truth** voor producten én voorraadstanden. De app leest producten + voorraad uit WooCommerce via een background sync thread (elke 5 min), schrijft voorraadwijzigingen terug via de REST API, en houdt een lokaal logboek bij in SQLite.

Er is geen lokale producten-tabel. Producten komen uit WooCommerce (background sync, in-memory cache).

## Tech stack
- Python + Flask (server-rendered Jinja2 templates)
- SQLite (users, withdrawals, withdrawal_items, log_entries tabellen)
- Tailwind CSS via CDN (geen build stap)
- WooCommerce REST API v3 (basic auth met consumer key/secret)
- PWA met manifest + app iconen

## Bestanden
```
app.py              — Flask app, alle routes
models.py           — SQLAlchemy modellen: User, Withdrawal, WithdrawalItem, LogEntry
auth.py             — login_required en admin_required decorators
woo_client.py       — WooCommerce API client met background sync thread
seed.py             — Script om gebruikers aan te maken
deploy.sh           — Deploy script naar voorraad.hetgenietschap.eu
passenger_wsgi.py   — WSGI entry point voor productie
requirements.txt    — Flask, Flask-SQLAlchemy, requests, python-dotenv, gunicorn
templates/
  base.html         — Layout, Tailwind CDN, nav, flash messages, PWA meta tags
  login.html        — Inlogformulier
  inventory.html    — Productlijst met voorraad + toggle "verberg niet op voorraad" + CTA
  reason.html       — Reden kiezen (proeverij/vergadering/custom)
  selection.html    — Flessen selecteren met +/− steppers
  done.html         — Bevestigingsscherm na afname
  delivery.html     — Levering registreren (admin-only)
  log.html          — Logboek per sessie met filters (reden, persoon)
static/
  style.css         — Minimale custom CSS (sheet transitions, safe areas)
  genietschap.png   — Logo
  manifest.json     — PWA manifest
  icons/            — App iconen (192, 512, 180, 32px)
```

## Afname-flow (mandje-model)
1. Gebruiker logt in → sessie-cookie geldig voor 365 dagen
2. Keldervoorraad toont producten + stock uit WooCommerce
3. Klik "Flessen meenemen" → kies reden (proeverij/vergadering/custom)
4. Selecteer flessen met +/− steppers → bevestig
5. Voorraad wordt per fles bijgewerkt in WooCommerce, Withdrawal + items opgeslagen in SQLite
6. Logboek toont afnames per sessie, filterbaar op reden en persoon

## Leveringen
Admin-only flow via apart scherm. Gebruikt LogEntry model met category="levering".

## Deploy
`bash deploy.sh` — rsync naar voorraad.hetgenietschap.eu + app restart via passenger.

## Taal
De UI is volledig in het Nederlands. Code comments en variabelen zijn in het Engels.
