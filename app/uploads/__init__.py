from flask import Blueprint

uploads_bp = Blueprint('uploads', __name__, url_prefix='/uploads')

from . import routes  # noqa: E402,F401
