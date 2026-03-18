from flask import Blueprint
comments_bp=Blueprint('comments',__name__,url_prefix='/comments')
from . import routes
