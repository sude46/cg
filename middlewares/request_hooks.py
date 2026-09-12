import time
import uuid

from flask import g, request


def before_request_hook():
    g.request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
    g.start_time = time.time()
    g.log_extra = {
        'request_id': g.request_id,
        'user_id': None,
        'start_time': g.start_time
    }

def after_request_hook(response):
    if hasattr(g, 'log_extra') and 'start_time' in g.log_extra:
        elapsed = time.time() - g.log_extra['start_time']
        g.log_extra['elapsed_time'] = elapsed
    else:
        g.log_extra = {'elapsed_time': 0}
    return response

def register_request_hook(app):
    app.before_request(before_request_hook)
    app.after_request(after_request_hook)

