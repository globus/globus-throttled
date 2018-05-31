"""
Simple example API which uses globus_throttled to implement rate limiting.
Tries to limit by Authorization header, and if that fails tries to use the
requester's IP.

Uses flask + requests
"""

from flask import Flask, request, jsonify
from functools import wraps
import requests
import time

app = Flask(__name__)
sess = requests.Session()


class RateLimitError(Exception):
    pass


def render_rate_limit_err(err):
    response = jsonify({'code': 'RateLimitExceeded', 'status': 429})
    response.status_code = 429
    return response


app.register_error_handler(RateLimitError, render_rate_limit_err)


def _check_rate_limit(requester_id, resource_id):
    start = time.time()
    response = sess.post(
        'http://localhost:8888/',
        json={'requester_id': requester_id, 'resource_id': resource_id})
    stop = time.time()
    print('throttler request took {}s'.format(stop - start))
    if not response.json()['allow_request']:
        raise RateLimitError()


def rate_limited(resource_id):
    def decorator(f):
        @wraps(f)
        def inner_func(*args, **kwargs):
            requester_id = request.headers.get('Authorization', None)
            if not requester_id:
                requester_id = request.remote_addr

            _check_rate_limit(requester_id, resource_id)

            return f(*args, **kwargs)

        return inner_func

    return decorator


@app.route('/')
@rate_limited('api:path:foo')
def hello_world():
    return 'hello world\n'
