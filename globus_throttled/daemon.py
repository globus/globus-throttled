#!/usr/bin/env python
import tornado.escape
import tornado.httpserver
import tornado.ioloop
import tornado.netutil
import tornado.web

from globus_throttled.throttler import Throttler


class RootTornadoHandler(tornado.web.RequestHandler):
    """
    This is a Tornado web request handler for requests made to the service
    root, i.e. "/"
    It is initialized with a throttler object to track state.

    Only accepts POST requests, which must send a requester ID and a resource
    ID encoded in a JSON body. The request is decoded and passed to the
    throttler's handle_event method.
    The results of that call are written back to the caller verbatim.
    """
    def initialize(self, throttler):
        """
        Setup the handler. Only runs once per Tornado Server.
        """
        self.throttler = throttler

    def post(self):
        """
        Handle POST /
        Runs on every request.
        """
        request = tornado.escape.json_decode(self.request.body)
        self.write(self.throttler.handle_event(request))


def make_tornado_app(throttler):
    """
    Given a throttler, create a Tornado application with its routes mapped to
    various handlers.
    Right now, just maps / to the root handler.
    """
    return tornado.web.Application([
        ('/', RootTornadoHandler, {'throttler': throttler}),
    ])


def run_daemon(sock_mode='net', sock_port=8888, sock_path=None):
    """
    Does these steps:
    - make a new throttler
    - make a Tornado HTTP Server (synchronous, but non-blocking)
    - bind to a unix socket or a port
    - start Tornado listening
    """
    throttler = Throttler()
    server = tornado.httpserver.HTTPServer(make_tornado_app(throttler))

    # if in unix mode, bind a unix socket
    if sock_mode == 'unix':
        unix_socket = tornado.netutil.bind_unix_socket(sock_path)
        server.add_socket(unix_socket)
    # if in net mode, bind to the given port num
    elif sock_mode == 'net':
        norm_sockets = tornado.netutil.bind_sockets(sock_port)
        server.add_sockets(norm_sockets)
    # otherwise, we were given a back sock_mode
    else:
        raise ValueError('Invalid sock_mode: {}'.format(sock_mode))

    # invoke the throttler cleanup ever 5s
    tornado.ioloop.PeriodicCallback(throttler.cleanup, 5000).start()

    tornado.ioloop.IOLoop.instance().start()


if __name__ == '__main__':
    run_daemon()
