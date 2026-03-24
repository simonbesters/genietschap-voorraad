# Task: Boekingen uitbreiden met status, vaartocht-types en prijs

## Context
Het Genietschap voorraadsysteem (Flask + WooCommerce). Kelderbeheerder Jonathan wil meer structuur in het boekingenscherm — statussen bijhouden, onderscheid maken tussen vaartochten met/zonder drank, en een prijs kunnen noteren.

## Design-referentie
In `tasks/genietschap-boekingen-v7_1.html` staat een statisch HTML-prototype met het gewenste design. **Gebruik dit als referentie voor layout, structuur en UX — niet voor namen of voorbeelddata.** Belangrijke design-patronen uit het prototype:

### Agenda-kaart (lijst)
- Klantnaam linksboven, datum rechtsboven
- Badges-rij eronder: type-badge + status-badge naast elkaar
- Metadata-rij: tijd, aantal personen, prijs (als ingevuld), locatie
- Crew-footer met avatars en namen, gescheiden door dots. Warning "nog X nodig" rechts uitgelijnd
- Kaart is klikbaar → gaat naar detail (dit is nu niet zo, maar kan later)

### Formulier
- **Type-selectie als 2×2 grid van kaarten** met icoon + label (niet een select/dropdown):
  - Proeverij: 🍷
  - Vaartocht + proeverij: ⛵🥂
  - Vaartocht: ⛵
  - Zelf varen: 🚤
  - Geselecteerde kaart krijgt dikke border (`border-2 border-gray-900`)
- **Status als pill-chips** (styled radio buttons in een rij):
  - Offerte: grijs (`bg-gray-100 text-gray-500 border-gray-400`)
  - Bevestigd: groen (`bg-emerald-50 text-emerald-600 border-emerald-600`)
  - Voorlopig: oranje (`bg-orange-50 text-orange-500 border-orange-500`)
  - Geselecteerde pill krijgt gekleurde achtergrond + border + bold
- **Prijs**: gewoon tekstveld met placeholder "bijv. €250 of €35 p.p."
- **Bemanning**: toggle-buttons per lid (niet dropdown), geselecteerd = groene achtergrond
- Veldvolgorde: Type → Status → Klant → Telefoon → Datum+Tijd (naast elkaar) → Aantal personen → Prijs → Locatie (pills) → Bemanning → Opmerkingen

### Filter-chips op agenda
- "Alles" + per type een chip, consistent met logboek-stijl
- "Vaartocht" chip filtert op beide vaartocht-types

## Huidige situatie
- Model `Booking` in `models.py` met velden: `booking_type`, `client_name`, `client_phone`, `date`, `time_description`, `group_size`, `location`, `notes`
- `booking_type` is één van: `proeverij`, `vaartocht`, `zelfvaren`
- Er is een automatische `is_voorlopig` property die checkt of er genoeg crew is toegewezen — dit is iets anders dan de klant-status die Jonathan bedoelt
- Template `templates/agenda.html` toont boekingen als kaarten met datum, type-badge, klantinfo en crew-toewijzing
- Aanmaken/bewerken via routes `agenda_new` en `agenda_edit` in `app.py`

## Wijzigingen

### 1. Status-veld toevoegen
Nieuw veld `status` op het `Booking` model voor de klant-status van de boeking.

**Specificaties:**
- Nieuw kolom `status = db.Column(db.String(20), nullable=False, default="offerte")`
- Opties: `offerte`, `bevestigd`, `voorlopig`
- Display labels: `{"offerte": "Offerte", "bevestigd": "Bevestigd", "voorlopig": "Voorlopig"}`
- Status-badge styling (zie design-referentie hierboven)
- In het formulier: pill-chips (zie design-referentie)
- In de agenda-kaart: status-badge naast de type-badge
- De bestaande `is_voorlopig` property (crew-bezetting) hernoemen naar `needs_crew` om verwarring met de nieuwe status te voorkomen. Update ook de template waar `is_voorlopig` gebruikt wordt.

### 2. Vaartocht-types splitsen
Onderscheid maken tussen vaartochten met en zonder drank.

**Specificaties:**
- `booking_type` opties uitbreiden van `proeverij, vaartocht, zelfvaren` naar: `proeverij, vaartocht_met_drank, vaartocht_zonder_drank, zelfvaren`
- `_TYPE_LABELS` updaten: `{"proeverij": "Proeverij", "vaartocht_met_drank": "Vaartocht + proeverij", "vaartocht_zonder_drank": "Vaartocht", "zelfvaren": "Zelf varen"}`
- `min_crew` property aanpassen: beide vaartocht-types vereisen 2 crew
- In het formulier: 2×2 grid met type-kaarten (zie design-referentie)
- Badge styling in de template: beide vaartocht-types krijgen blauwe styling (`bg-blue-50 text-blue-600`), check aanpassen van `== 'vaartocht'` naar `b.booking_type.startswith('vaartocht')`
- Filter-chips op agenda: "Vaartocht" chip filtert op beide vaartocht-types
- Bestaande boekingen met `booking_type="vaartocht"` migreren naar `vaartocht_met_drank`

### 3. Prijsveld toevoegen
Optioneel vrij tekstveld voor de prijs.

**Specificaties:**
- Nieuw kolom `price = db.Column(db.String(50), nullable=True)`
- In het formulier: tekst-input met placeholder "bijv. €250 of €35 p.p."
- In de agenda-kaart: tonen in de metadata-rij (naast tijd, groepsgrootte, locatie), alleen als het ingevuld is

## Bestanden die geraakt worden
- `models.py` — `Booking` model: nieuw `status` en `price` kolom, `booking_type` opties uitbreiden, `is_voorlopig` hernoemen naar `needs_crew`
- `app.py` — `agenda_new` en `agenda_edit` routes: nieuwe velden verwerken, migratie van bestaande vaartocht-records
- `templates/agenda.html` — status-badge, aangepaste type-badges, filter-chips, prijs tonen, `is_voorlopig` → `needs_crew`
- `templates/agenda_form.html` (of het formulier-template) — type-grid, status-pills, prijsveld

## Database migratie
SQLite `db.create_all()` voegt nieuwe nullable kolommen toe, maar niet kolommen met NOT NULL + default. Aanbevolen aanpak:

```python
# In app.py na db.create_all()
from sqlalchemy import text, inspect

with db.engine.connect() as conn:
    # Add new columns if they don't exist yet
    cols = [c["name"] for c in inspect(db.engine).get_columns("bookings")]
    if "status" not in cols:
        conn.execute(text("ALTER TABLE bookings ADD COLUMN status VARCHAR(20) DEFAULT 'offerte'"))
    if "price" not in cols:
        conn.execute(text("ALTER TABLE bookings ADD COLUMN price VARCHAR(50)"))
    # Migrate existing vaartocht bookings
    conn.execute(text("UPDATE bookings SET booking_type='vaartocht_met_drank' WHERE booking_type='vaartocht'"))
    conn.commit()
```

## Test
- Nieuwe boeking aanmaken → type-grid, status-pills, en prijs zijn zichtbaar en werken
- Bestaande boeking bewerken → status en prijs toevoegen, type wijzigen
- Agenda-kaart toont status-badge (kleur per status), correct type-label, en prijs
- Filter-chip "Vaartocht" toont beide vaartocht-types
- Bestaande vaartocht-boekingen zijn gemigreerd naar "Vaartocht + proeverij"
- Crew-indicator ("nog X nodig") werkt voor beide vaartocht-types
