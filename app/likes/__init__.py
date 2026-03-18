from flask import Blueprint

likes_bp=Blueprint('likes',__name__, url_prefix='/likes')
from . import routes
