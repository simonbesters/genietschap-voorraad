from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)

    log_entries = db.relationship("LogEntry", backref="user", lazy=True)
    withdrawals = db.relationship("Withdrawal", backref="user", lazy=True)
    booking_assignments = db.relationship("BookingAssignment", backref="user", lazy=True)

    def __repr__(self):
        return f"<User {self.username}>"


class LogEntry(db.Model):
    """Used for deliveries (levering) only."""
    __tablename__ = "log_entries"

    id = db.Column(db.Integer, primary_key=True)
    woo_product_id = db.Column(db.Integer, nullable=False)
    product_name = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<LogEntry {self.product_name} {self.quantity:+d}>"


class Withdrawal(db.Model):
    """A session-based withdrawal: one reason, multiple items."""
    __tablename__ = "withdrawals"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    reason = db.Column(db.String(50), nullable=False)  # proeverij, vergadering, overig
    custom_reason = db.Column(db.String(200), nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    items = db.relationship(
        "WithdrawalItem", backref="withdrawal", lazy=True, cascade="all, delete-orphan"
    )

    @property
    def reason_display(self):
        if self.reason == "overig" and self.custom_reason:
            return self.custom_reason
        return self.reason.capitalize()

    @property
    def total_bottles(self):
        return sum(item.quantity for item in self.items)

    def __repr__(self):
        return f"<Withdrawal {self.id} by user {self.user_id}>"


class WithdrawalItem(db.Model):
    __tablename__ = "withdrawal_items"

    id = db.Column(db.Integer, primary_key=True)
    withdrawal_id = db.Column(
        db.Integer, db.ForeignKey("withdrawals.id"), nullable=False
    )
    woo_product_id = db.Column(db.Integer, nullable=False)
    product_name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f"<WithdrawalItem {self.product_name} x{self.quantity}>"


class Booking(db.Model):
    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)
    booking_type = db.Column(db.String(20), nullable=False, default="proeverij")  # proeverij, vaartocht, zelfvaren
    client_name = db.Column(db.String(200), nullable=False)
    client_phone = db.Column(db.String(20), nullable=True)
    date = db.Column(db.Date, nullable=False)
    time_description = db.Column(db.String(100), nullable=True)
    group_size = db.Column(db.String(100), nullable=True)
    location = db.Column(db.String(300), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    creator = db.relationship("User", backref="bookings_created")
    assignments = db.relationship(
        "BookingAssignment", backref="booking", lazy=True, cascade="all, delete-orphan"
    )

    _TYPE_LABELS = {"proeverij": "Proeverij", "vaartocht": "Vaartocht", "zelfvaren": "Zelf varen"}

    @property
    def type_display(self):
        return self._TYPE_LABELS.get(self.booking_type, self.booking_type)

    @property
    def assigned_users(self):
        return [a.user for a in self.assignments]

    @property
    def min_crew(self):
        return 2 if self.booking_type == "vaartocht" else 1

    @property
    def is_voorlopig(self):
        return len(self.assignments) < self.min_crew

    def __repr__(self):
        return f"<Booking {self.id} {self.client_name} {self.date}>"


class BookingAssignment(db.Model):
    __tablename__ = "booking_assignments"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
