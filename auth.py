from functools import wraps
from flask import session, redirect, url_for, request, flash


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", next=request.url))
        if not session.get("is_admin"):
            flash("Je hebt geen rechten voor deze actie.", "error")
            return redirect(url_for("inventory"))
        return f(*args, **kwargs)
    return decorated_function
