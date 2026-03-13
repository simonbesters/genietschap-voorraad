import json
import os
import re
from datetime import date, timedelta

from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

from auth import admin_required, login_required
from models import Booking, BookingAssignment, LogEntry, User, Withdrawal, WithdrawalItem, db
from woo_client import get_product, get_products, queue_stock_update, start_sync, update_stock

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///voorraad.db"
)
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=365)

db.init_app(app)

with app.app_context():
    db.create_all()

start_sync()


# --- Product name parser ---

_NAME_RE = re.compile(r"^(.+?)\s[-–—]\s(.+?)(?:\s*\(([^)]+)\))?\s*$")


_BRAND_INITIALS = {
    "marcel moineaux": "MM",
    "domaine guilleman": "GM",
    "champagne tornay": "TO",
    "rené & michel koch": "KO",
    "jean plener": "PL",
    "jean-pol hautbois": "HB",
}


@app.template_global()
def parse_product_name(name):
    """Parse 'Huis - Type (Volume)' into parts."""
    m = _NAME_RE.match(name)
    if m:
        return {"house": m.group(1).strip(), "type": m.group(2).strip(), "volume": (m.group(3) or "").strip()}
    return {"house": name, "type": "", "volume": ""}


@app.template_global()
def brand_initials(house):
    """Return 2-letter initials for a brand/house name."""
    return _BRAND_INITIALS.get(house.lower().strip(), house[:2].upper())


_AVATAR_COLORS = ["#5b7f67", "#7c6ca8", "#c0784e", "#4a8db7", "#b85c5c", "#8a7d6b"]

_NL_MONTHS = [
    "", "jan", "feb", "mrt", "apr", "mei", "jun",
    "jul", "aug", "sep", "okt", "nov", "dec",
]
_NL_MONTHS_FULL = [
    "", "januari", "februari", "maart", "april", "mei", "juni",
    "juli", "augustus", "september", "oktober", "november", "december",
]
_NL_WEEKDAYS = ["ma", "di", "wo", "do", "vr", "za", "zo"]


@app.template_global()
def avatar_color(user_id):
    """Return a consistent color for a user avatar."""
    return _AVATAR_COLORS[user_id % len(_AVATAR_COLORS)]


@app.template_global()
def user_initials(display_name):
    """Return first letter of display name."""
    return display_name[0].upper() if display_name else "?"


@app.template_global()
def nl_month(d):
    """Return Dutch abbreviated month for a date."""
    return _NL_MONTHS[d.month].upper()


@app.template_global()
def nl_month_full(d):
    """Return full Dutch month name for a date."""
    return _NL_MONTHS_FULL[d.month]


@app.template_global()
def nl_weekday(d):
    """Return Dutch abbreviated weekday for a date."""
    return _NL_WEEKDAYS[d.weekday()]


# --- Auth routes ---


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("inventory"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session.permanent = True
            session["user_id"] = user.id
            session["display_name"] = user.display_name
            session["is_admin"] = user.is_admin
            next_url = request.args.get("next") or url_for("inventory")
            return redirect(next_url)

        flash("Ongeldige gebruikersnaam of wachtwoord.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# --- Inventory ---


@app.route("/")
@login_required
def inventory():
    try:
        products = get_products()
    except Exception as e:
        flash(f"Kon producten niet ophalen uit WooCommerce: {e}", "error")
        products = []
    return render_template("inventory.html", products=products)


# --- Withdrawal flow ---


@app.route("/afname")
@login_required
def withdrawal_reason():
    return render_template("reason.html")


@app.route("/afname/selectie")
@login_required
def withdrawal_select():
    reason = request.args.get("reden", "").strip()
    custom = request.args.get("tekst", "").strip()

    if not reason:
        return redirect(url_for("withdrawal_reason"))

    try:
        products = get_products()
    except Exception as e:
        flash(f"Kon producten niet ophalen: {e}", "error")
        products = []

    # Only show in-stock products, sorted by name
    in_stock = sorted(
        [p for p in products if p.get("stock_quantity") and p["stock_quantity"] > 0],
        key=lambda p: p["name"].lower(),
    )

    return render_template(
        "selection.html",
        products=in_stock,
        reason=reason,
        custom_reason=custom,
    )


@app.route("/afname/bevestig", methods=["POST"])
@login_required
def withdrawal_confirm():
    reason = request.form.get("reason", "").strip()
    custom_reason = request.form.get("custom_reason", "").strip() or None
    items_json = request.form.get("items", "[]")

    if not reason:
        flash("Geen reden opgegeven.", "error")
        return redirect(url_for("withdrawal_reason"))

    try:
        items = json.loads(items_json)
    except (json.JSONDecodeError, TypeError):
        flash("Ongeldige selectie.", "error")
        return redirect(url_for("withdrawal_reason"))

    if not items:
        flash("Geen flessen geselecteerd.", "error")
        return redirect(url_for("withdrawal_reason"))

    # Create the withdrawal session
    withdrawal = Withdrawal(
        user_id=session["user_id"],
        reason=reason,
        custom_reason=custom_reason,
    )

    try:
        for item in items:
            product_id = int(item["id"])
            quantity = int(item["qty"])

            if quantity < 1:
                continue

            product = get_product(product_id)

            # Server-side validation: don't exceed stock
            if quantity > product["stock_quantity"]:
                quantity = product["stock_quantity"]
            if quantity < 1:
                continue

            new_stock = product["stock_quantity"] - quantity
            queue_stock_update(product_id, new_stock)

            withdrawal.items.append(WithdrawalItem(
                woo_product_id=product_id,
                product_name=product["name"],
                quantity=quantity,
            ))

        if not withdrawal.items:
            flash("Geen geldige flessen om af te boeken.", "error")
            return redirect(url_for("withdrawal_reason"))

        db.session.add(withdrawal)
        db.session.commit()

        return render_template("done.html", withdrawal=withdrawal)

    except Exception as e:
        db.session.rollback()
        flash(f"Fout bij registreren: {e}", "error")
        return redirect(url_for("inventory"))


# --- Delivery (admin only) ---


@app.route("/levering", methods=["GET", "POST"])
@admin_required
def delivery():
    try:
        products = get_products()
    except Exception as e:
        flash(f"Kon producten niet ophalen: {e}", "error")
        products = []

    # Sort alphabetically by name for delivery
    products = sorted(products, key=lambda p: p["name"].lower())

    if request.method == "POST":
        items_json = request.form.get("items", "[]")
        note = request.form.get("note", "").strip() or None

        try:
            items = json.loads(items_json)
        except (json.JSONDecodeError, TypeError):
            flash("Ongeldige selectie.", "error")
            return render_template("delivery.html", products=products)

        if not items:
            flash("Geen producten geselecteerd.", "error")
            return render_template("delivery.html", products=products)

        try:
            total = 0
            for item in items:
                product_id = int(item["id"])
                quantity = int(item["qty"])
                if quantity < 1:
                    continue

                product = get_product(product_id)
                new_stock = product["stock_quantity"] + quantity
                queue_stock_update(product_id, new_stock)

                entry = LogEntry(
                    woo_product_id=product_id,
                    product_name=product["name"],
                    user_id=session["user_id"],
                    quantity=quantity,
                    category="levering",
                    note=note,
                )
                db.session.add(entry)
                total += quantity

            db.session.commit()
            flash(f"Levering geregistreerd: +{total} flessen.", "success")
            return redirect(url_for("delivery"))

        except Exception as e:
            db.session.rollback()
            flash(f"Fout bij registreren: {e}", "error")

    return render_template("delivery.html", products=products)


# --- Log ---


@app.route("/logboek")
@login_required
def log():
    query = Withdrawal.query

    reason_filter = request.args.get("reden", "")
    user_filter = request.args.get("user", "")

    if reason_filter:
        query = query.filter(Withdrawal.reason == reason_filter)
    if user_filter:
        query = query.filter(Withdrawal.user_id == int(user_filter))

    withdrawals = query.order_by(Withdrawal.created_at.desc()).limit(100).all()
    users = User.query.order_by(User.display_name).all()

    return render_template(
        "log.html",
        withdrawals=withdrawals,
        users=users,
        reason_filter=reason_filter,
        user_filter=user_filter,
    )


# --- Agenda / Bookings ---


@app.route("/agenda")
@login_required
def agenda():
    today = date.today()
    upcoming = (
        Booking.query
        .filter(Booking.date >= today)
        .order_by(Booking.date.asc())
        .all()
    )
    past = (
        Booking.query
        .filter(Booking.date < today)
        .order_by(Booking.date.desc())
        .all()
    )
    users = User.query.order_by(User.display_name).all()
    return render_template("agenda.html", upcoming=upcoming, past=past, users=users, today=today)


@app.route("/agenda/nieuw", methods=["GET", "POST"])
@login_required
def agenda_new():
    if request.method == "POST":
        client_name = request.form.get("client_name", "").strip()
        if not client_name:
            flash("Klantnaam is verplicht.", "error")
            return redirect(url_for("agenda_new"))

        date_str = request.form.get("date", "").strip()
        if not date_str:
            flash("Datum is verplicht.", "error")
            return redirect(url_for("agenda_new"))

        try:
            booking_date = date.fromisoformat(date_str)
        except ValueError:
            flash("Ongeldige datum.", "error")
            return redirect(url_for("agenda_new"))

        booking_type = request.form.get("booking_type", "proeverij")
        if booking_type == "proeverij":
            location = request.form.get("location", "").strip() or None
        else:
            location = None

        booking = Booking(
            booking_type=booking_type,
            client_name=client_name,
            client_phone=request.form.get("client_phone", "").strip() or None,
            date=booking_date,
            time_description=request.form.get("time_description", "").strip() or None,
            group_size=request.form.get("group_size", "").strip() or None,
            location=location,
            notes=request.form.get("notes", "").strip() or None,
            created_by=session["user_id"],
        )
        db.session.add(booking)
        db.session.flush()

        member_ids = request.form.getlist("members")
        for uid in member_ids:
            db.session.add(BookingAssignment(booking_id=booking.id, user_id=int(uid)))

        db.session.commit()
        flash("Boeking aangemaakt.", "success")
        return redirect(url_for("agenda"))

    users = User.query.order_by(User.display_name).all()
    return render_template("booking_form.html", booking=None, users=users)


@app.route("/agenda/<int:booking_id>/bewerk", methods=["GET", "POST"])
@login_required
def agenda_edit(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if request.method == "POST":
        client_name = request.form.get("client_name", "").strip()
        if not client_name:
            flash("Klantnaam is verplicht.", "error")
            return redirect(url_for("agenda_edit", booking_id=booking_id))

        date_str = request.form.get("date", "").strip()
        if not date_str:
            flash("Datum is verplicht.", "error")
            return redirect(url_for("agenda_edit", booking_id=booking_id))

        try:
            booking_date = date.fromisoformat(date_str)
        except ValueError:
            flash("Ongeldige datum.", "error")
            return redirect(url_for("agenda_edit", booking_id=booking_id))

        booking_type = request.form.get("booking_type", "proeverij")
        if booking_type == "proeverij":
            location = request.form.get("location", "").strip() or None
        else:
            location = None

        booking.booking_type = booking_type
        booking.client_name = client_name
        booking.client_phone = request.form.get("client_phone", "").strip() or None
        booking.date = booking_date
        booking.time_description = request.form.get("time_description", "").strip() or None
        booking.group_size = request.form.get("group_size", "").strip() or None
        booking.location = location
        booking.notes = request.form.get("notes", "").strip() or None

        BookingAssignment.query.filter_by(booking_id=booking.id).delete()
        member_ids = request.form.getlist("members")
        for uid in member_ids:
            db.session.add(BookingAssignment(booking_id=booking.id, user_id=int(uid)))

        db.session.commit()
        flash("Boeking bijgewerkt.", "success")
        return redirect(url_for("agenda"))

    users = User.query.order_by(User.display_name).all()
    return render_template("booking_form.html", booking=booking, users=users)


@app.route("/agenda/<int:booking_id>/verwijder", methods=["POST"])
@login_required
def agenda_delete(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    db.session.delete(booking)
    db.session.commit()
    flash("Boeking verwijderd.", "success")
    return redirect(url_for("agenda"))


@app.route("/agenda/<int:booking_id>/opgeven", methods=["POST"])
@login_required
def agenda_assign(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    user_id = int(request.form.get("user_id", session["user_id"]))

    existing = BookingAssignment.query.filter_by(
        booking_id=booking_id, user_id=user_id
    ).first()

    if existing:
        db.session.delete(existing)
        db.session.commit()
    else:
        assignment = BookingAssignment(booking_id=booking_id, user_id=user_id)
        db.session.add(assignment)
        db.session.commit()

    return redirect(url_for("agenda"))


# --- Undo withdrawal (admin only) ---


@app.route("/logboek/<int:withdrawal_id>/terugdraaien", methods=["POST"])
@admin_required
def undo_withdrawal(withdrawal_id):
    withdrawal = Withdrawal.query.get_or_404(withdrawal_id)
    try:
        for item in withdrawal.items:
            product = get_product(item.woo_product_id)
            new_stock = product["stock_quantity"] + item.quantity
            queue_stock_update(item.woo_product_id, new_stock)

        total = withdrawal.total_bottles
        db.session.delete(withdrawal)
        db.session.commit()

        flash(f"Afname teruggedraaid ({total} flessen terug in voorraad).", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Fout bij terugdraaien: {e}", "error")

    return redirect(url_for("log"))


if __name__ == "__main__":
    app.run(debug=True)
