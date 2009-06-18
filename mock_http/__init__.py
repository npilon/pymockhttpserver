#!/usr/bin/env python

import BaseHTTPServer
import threading
import urllib2
from collections import defaultdict
import select
import socket

GET = 'GET'
POST = 'POST'

never = object()
once = object()
at_least_once = object()

class TimeoutHTTPServer(BaseHTTPServer.HTTPServer):
    """HTTPServer class with timeout."""

    def get_request(self):
        """Get the request and client address from the socket."""
        # 0.1 second timeout
        self.socket.settimeout(0.1)
        result = self.socket.accept()
        result[0].settimeout(None)
        return result

def _server_thread(server, started, finish_serving, finished_serving):
    started.set()
    while not finish_serving.isSet():
        try:
            server.handle_request()
        except:
            pass
    server.server_close()
    finished_serving.set()

class MockHTTPException(Exception):
    pass

class UnexpectedURLException(Exception):
    """Raised by verify when MockHTTP had gotten an unexpected URL."""
    pass

class UnretrievedURLException(Exception):
    """Raised by verify when MockHTTP has not gotten a request for a URL."""
    pass

class URLOrderingException(Exception):
    """Raised by verify when MockHTTP got requests for URLs in the wrong order."""
    pass

class Expectation(object):
    def __init__(self, mock, method, path, body='', headers=None, times=None,
                 name=None, after=None):
        self.mock = mock
        self.method = method
        self.path = path
        self.request_body = body
        self.request_headers = headers
        self.response_code = 200
        self.response_headers = {}
        self.response_body = ''
        self.times = times
        self.invoked = False
        self.name = name
        if name is not None:
            self.mock.expected_by_name[name] = self
        if after is not None:
            self.after = self.mock.expected_by_name[after]
        else:
            self.after = None
    
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
        server = TimeoutHTTPServer(
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
        self.out_of_order = False
        self.expected = defaultdict(dict)
        self.expected_by_name = {}
    
    def expects(self, method, path, *args, **kwargs):
        expectation = Expectation(self, method, path, *args, **kwargs)
        self.expected[method][path] = expectation
        return expectation
    
    def verify(self):
        self.finish_serving.set()
        self.finished_serving.wait()
        if not self.finished_serving.isSet():
            raise MockHTTPException('Server has not shut down.')
        if self.out_of_order:
            raise URLOrderingException()
        if self.failed_url:
            raise UnexpectedURLException('Got unexpected URL: %s' % self.failed_url)
        for method, expected in self.expected.iteritems():
            for path, expectation in expected.iteritems():
                if (expectation.times is once or\
                    expectation.times is at_least_once) and\
                   not expectation.invoked:
                    raise UnretrievedURLException("%s not %s'd" % (path, method))
        return True

class RequestHandler(BaseHTTPServer.BaseHTTPRequestHandler, object):
    rbufsize = 0
    
    def __init__(self, mock, *args, **kwargs):
        self.mock = mock
        super(RequestHandler, self).__init__(*args, **kwargs)
    
    def __getattr__(self, name):
        if name.startswith('do_'):
            method = name[3:]
            return lambda: self.do(method)
    
    def fail(self, message=None):
        self.mock.failed_url = self.path
        self.send_response(404, message)
        self.end_headers()
        self.wfile.write('')
    
    def do(self, method):
        if self.path not in self.mock.expected[method]:
            self.fail('Unexpected URL: %s' % self.path)
        else:
            expectation = self.mock.expected[method][self.path]
            if expectation.request_headers:
                for header, value in expectation.request_headers.iteritems():
                    if header not in self.headers:
                        self.fail('Expected header missing: %s' % header)
                    elif self.headers[header] != value:
                        self.fail('Wrong value for %s. Expected: %r Got: %r' %\
                                  (header, self.headers[header], value))
            request_body = ''
            while select.select([self.rfile], [], [], 0.5)[0]:
                request_body += self.rfile.read(1)
            if request_body != expectation.request_body:
                self.fail('Unexpected request body. Expected: %r Got: %r' %\
                          (expectation.request_body, request_body))
            if expectation.times is never:
                self.fail('%s %s, expected never' % (method, self.path))
            elif expectation.times is once and expectation.invoked:
                self.fail('%s %s twice, expected once' % (method, self.path))
            if expectation.after is not None and\
               not expectation.after.invoked:
                self.mock.out_of_order = True
                self.fail('%s %s expected only after %s %s' %
                          (method, self.path, expectation.after.method,
                           expectation.after.path))
            self.send_response(expectation.response_code)
            for header, value in expectation.response_headers.iteritems():
                self.send_header(header, value)
            self.end_headers()
            self.wfile.write(expectation.response_body)
            expectation.invoked = True
