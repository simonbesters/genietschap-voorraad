# Task: Verwerk kelderbeheerder-feedback

## Context
Het Genietschap voorraadsysteem (Flask + WooCommerce). Kelderbeheerder Jonathan heeft feedback na eerste gebruik.

## Wijzigingen

### 1. Voorraadcorrectie-scherm (`/correctie`, admin-only)
Nieuw scherm waarmee Jonathan de werkelijke voorraad kan invoeren. Het systeem berekent zelf de delta en past WooCommerce aan.

**Specificaties:**
- Nieuwe route `/correctie` (GET + POST), `@admin_required`
- Toont alle producten (gesorteerd op naam) met huidige voorraad
- Per product een invoerveld waar de werkelijke stand ingevuld kan worden
- Placeholder = huidige voorraad, label "nu: X" ernaast
- Visuele feedback: rij kleurt groen bij meer, rood bij minder
- Confirm-bar onderaan met samenvatting (+X, −Y flessen) en optioneel notitieveld ("Reden correctie")
- POST verwerking: per product delta berekenen, `update_stock()` aanroepen, `LogEntry` aanmaken met `category="correctie"` en delta als quantity (kan negatief zijn)
- Nav link "Correctie" toevoegen in `base.html`, alleen zichtbaar voor admin (naast "Levering")
- Button kleur: amber (onderscheid van groene levering-button)

**Referentie:** Bouw het scherm analoog aan `templates/delivery.html` maar met absoluut invoerveld ipv relatief.

### 2. Sortering op productnaam
Twee plekken:

**a) Selectiescherm (`/afname/selectie`):**
- In `app.py` route `withdrawal_select`: sorteer `in_stock` lijst op `p["name"].lower()`

**b) Logboek items:**
- In `templates/log.html`: sorteer de items-loop op productnaam
- Jinja2: `{% for item in w.items|sort(attribute='product_name') %}`

### 3. Model docstring
- Update `LogEntry` docstring in `models.py`: wordt nu ook voor correcties gebruikt, niet alleen leveringen

## Bestanden die geraakt worden
- `app.py` — nieuwe route + sortering in withdrawal_select
- `models.py` — docstring
- `templates/base.html` — nav link
- `templates/correction.html` — nieuw bestand
- `templates/log.html` — sortering items

## Test
- Login als admin → "Correctie" zichtbaar in nav
- Vul bij 1-2 producten een afwijkende stand in → confirm-bar verschijnt
- Doorvoeren → flash message, WooCommerce stock bijgewerkt, LogEntry met category="correctie"
- Logboek: items staan nu op productnaam gesorteerd
- Selectiescherm: producten staan op naam gesorteerd
