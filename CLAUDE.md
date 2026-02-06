# Genietschap Voorraad — Project Handover

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
