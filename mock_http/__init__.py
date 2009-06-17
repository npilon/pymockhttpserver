#!/usr/bin/env python

import BaseHTTPServer
import threading
import urllib2
from collections import defaultdict

GET = object()

never = object()
once = object()
at_least_once = object()

def http_code(code):
    pass

def http_body(code):
    pass

def _server_thread(server, started, finish_serving, finished_serving):
    started.set()
    while not finish_serving.isSet():
        server.handle_request()
    server.server_close()
    finished_serving.set()

class MockHTTPException(Exception):
    pass

class UnexpectedURLException(Exception):
    """Raised by verify when MockHTTP had gotten an unexpected URL."""
    pass

class Expectation(object):
    def __init__(self, mock, method):
        self._mock = mock
        self._method = method
    
    def path(self, path):
        self._path = path
        self._mock.expected[self._method][self._path] = self

class MockHTTP(object):
    """A Mock HTTP Server for unit testing web services calls.
    
    Basic Usage::
    
         mock_server """
    
    def __init__(self, port):
        self.server_address = ('', port)
        started = threading.Event()
        self.finish_serving = threading.Event()
        self.finished_serving = threading.Event()
        server = BaseHTTPServer.HTTPServer(
            self.server_address, lambda *args, **kwargs: RequestHandler(
                self, *args, **kwargs))
        self.thread = threading.Thread(target=_server_thread,
                                       kwargs={'server': server,
                                               'started': started,
                                               'finish_serving': self.finish_serving,
                                               'finished_serving': self.finished_serving})
        self.thread.start()
        started.wait()
        self.failed_url = None
        self.expected = defaultdict(dict)
        self.expects(GET).path('/final_request')
    
    def expects(self, method):
        expectation = Expectation(self, method)
        return expectation
    
    def verify(self):
        self.finish_serving.set()
        urllib2.urlopen('http://localhost:%s/final_request' % self.server_address[1])
        self.finished_serving.wait('0.5')
        if not self.finished_serving.isSet():
            raise MockHTTPException('Server has not shut down.')
        if self.failed_url:
            raise UnexpectedURLException('Got unexpected URL: %s' % self.failed_url)
        return True

class RequestHandler(BaseHTTPServer.BaseHTTPRequestHandler, object):
    def __init__(self, mock, *args, **kwargs):
        self.mock = mock
        super(RequestHandler, self).__init__(*args, **kwargs)
    
    def do_GET(self):
        if self.path not in self.mock.expected[GET]:
            self.mock.failed_url = self.path
            self.send_response(404)
        else:
            self.send_response(200)
        self.end_headers()
        self.wfile.write('')
