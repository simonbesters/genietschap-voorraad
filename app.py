import json
import os
import re
from datetime import timedelta

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
from models import LogEntry, User, Withdrawal, WithdrawalItem, db
from woo_client import get_product, get_products, start_sync, update_stock

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

    # Only show in-stock products
    in_stock = [p for p in products if p.get("stock_quantity") and p["stock_quantity"] > 0]

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
            update_stock(product_id, new_stock)

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
                update_stock(product_id, new_stock)

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


# --- Undo withdrawal (admin only) ---


@app.route("/logboek/<int:withdrawal_id>/terugdraaien", methods=["POST"])
@admin_required
def undo_withdrawal(withdrawal_id):
    withdrawal = Withdrawal.query.get_or_404(withdrawal_id)
    try:
        for item in withdrawal.items:
            product = get_product(item.woo_product_id)
            new_stock = product["stock_quantity"] + item.quantity
            update_stock(item.woo_product_id, new_stock)

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
