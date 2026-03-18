from flask import Blueprint 

posts_bp=Blueprint('posts',__name__,url_prefix='/posts')
from . import routes
