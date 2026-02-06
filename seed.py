#!/usr/bin/env python3
"""Maak gebruikers aan (of reset). Voer uit:
   python seed.py
"""

from dotenv import load_dotenv

load_dotenv()

from werkzeug.security import generate_password_hash

from app import app
from models import User, db

USERS = [
    # (gebruikersnaam, wachtwoord, weergavenaam, is_admin)
    ("simon", "changeme", "Simon", True),
    ("jonathan", "changeme", "Jonathan", True),
    ("melcher", "changeme", "Melcher", False),
    ("richard", "changeme", "Richard", False),
    ("jesse", "changeme", "Jesse", False),
    ("marc", "changeme", "Marc", False),
]

with app.app_context():
    db.drop_all()
    db.create_all()
    for username, password, display_name, is_admin in USERS:
        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            display_name=display_name,
            is_admin=is_admin,
        )
        db.session.add(user)
        print(f"  Aangemaakt: {username} {'(admin)' if is_admin else ''}")
    db.session.commit()
    print("Klaar.")
