"""Authorization decorators."""

from __future__ import annotations

from functools import wraps

from flask import abort
from flask_login import current_user, login_required


def admin_required(view):
    """Require an authenticated administrator."""

    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped
