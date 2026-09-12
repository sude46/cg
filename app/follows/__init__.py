from flask import Blueprint

follows_bp=Blueprint('follows',__name__,url_prefix='/follows')
from . import routes  # noqa: E402,F401
