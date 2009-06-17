#!/usr/bin/env python

import BaseHTTPServer
import threading
import urllib2
from collections import defaultdict

GET = 'GET'

never = object()
once = object()
at_least_once = object()

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

class Action(object):
    pass

class Expectation(object):
    def __init__(self, mock, method, path):
        self.mock = mock
        self.method = method
        self.path = path
        self.http_code = 200
        self.http_headers = {}
        self.http_body = ''
    
    def will(self, http_code=None, headers=None, body=None):
        if http_code is not None:
            self.http_code = http_code
        if body is not None:
            self.http_body = body
        if headers is not None:
            self.http_headers = headers

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
        self.expects(method=GET, path='/final_request')
    
    def expects(self, method, path):
        expectation = Expectation(self, method, path)
        self.expected[method][path] = expectation
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
    
    def __getattr__(self, name):
        if name.startswith('do_'):
            method = name[3:]
            return lambda: self.do(method)
    
    def do(self, method):
        if self.path not in self.mock.expected[method]:
            self.mock.failed_url = self.path
            self.send_response(404)
            self.end_headers()
            self.wfile.write('')
        else:
            expectation = self.mock.expected[method][self.path]
            self.send_response(expectation.http_code)
            for header, value in expectation.http_headers.iteritems():
                self.send_header(header, value)
            self.end_headers()
            self.wfile.write(expectation.http_body)
