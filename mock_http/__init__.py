#!/usr/bin/env python

import BaseHTTPServer
import threading
import urllib2
from collections import defaultdict
import select

GET = 'GET'
POST = 'POST'

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
    def __init__(self, mock, method, path, body=None, headers=None):
        self.mock = mock
        self.method = method
        self.path = path
        self.request_body = body
        self.request_headers = headers
        if body:
            if not self.request_headers:
                self.request_headers = {}
            self.request_headers['content-length'] = str(len(body))
        self.response_code = 200
        self.response_headers = {}
        self.response_body = ''
    
    def will(self, http_code=None, headers=None, body=None):
        if http_code is not None:
            self.response_code = http_code
        if body is not None:
            self.response_body = body
        if headers is not None:
            self.response_headers = headers
        return self

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
    
    def expects(self, method, path, *args, **kwargs):
        expectation = Expectation(self, method, path, *args, **kwargs)
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
    
    def fail(self):
        self.mock.failed_url = self.path
        self.send_response(404)
        self.end_headers()
        self.wfile.write('')
    
    def do(self, method):
        if self.path not in self.mock.expected[method]:
            self.fail()
        else:
            expectation = self.mock.expected[method][self.path]
            if expectation.request_headers:
                for header, value in expectation.request_headers.iteritems():
                    if header not in self.headers or self.headers[header] != value:
                        self.fail()
            request_body = None
            if 'content-length' in self.headers:
                request_body = self.rfile.read(int(self.headers['content-length']))
            if request_body != expectation.request_body:
                self.fail()
            self.send_response(expectation.response_code)
            for header, value in expectation.response_headers.iteritems():
                self.send_header(header, value)
            self.end_headers()
            self.wfile.write(expectation.response_body)
