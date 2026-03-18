from flask import Blueprint

feeds_bp = Blueprint('feeds', __name__, url_prefix='/feeds')

@feeds_bp.route('/timeline')
def timeline():
    return {"msg": "timeline endpoint"}
