from flask import Blueprint

feeds_bp = Blueprint('feeds', __name__, url_prefix='/feeds')
from . import routes  # noqa: E402,F401
