#!/usr/bin/env python

"""Build a mock HTTP server that really works to unit test web service-dependent programs."""

import BaseHTTPServer
import threading
import urllib2
from collections import defaultdict
import select
import socket

__all__ = ['GET', 'POST', 'PUT', 'DELETE', 'never', 'once', 'at_least_once',
           'MockHTTP']

GET = 'GET'
POST = 'POST'
PUT = 'PUT'
DELETE = 'DELETE'

never = object()
once = object()
at_least_once = object()

class TimeoutHTTPServer(BaseHTTPServer.HTTPServer):
    """HTTPServer class with timeout."""

    def get_request(self):
        # 0.1 second timeout
        self.socket.settimeout(0.1)
        result = self.socket.accept()
        result[0].settimeout(None)
        return result

def _server_thread(server, started, finish_serving, finished_serving):
    """Handle requests to our server in another thread."""
    started.set()
    while not finish_serving.isSet():
        try:
            server.handle_request()
        except:
            pass
    server.server_close()
    finished_serving.set()

class MockHTTPException(Exception):
    """Raised when something unexpected goes wrong in MockHTTP's guts."""
    pass

class MockHTTPExpectationFailure(Exception):
    """Parent class for exceptions describing how a MockHTTP has failed to live
    up to expectations."""
    pass

class UnexpectedURLException(MockHTTPExpectationFailure):
    """Raised when MockHTTP had gotten a request for an unexpected URL."""
    pass

class AlreadyRetrievedURLException(MockHTTPExpectationFailure):
    """Raised when MockHTTP has gotten a request for a URL that can't be retrieved again."""
    pass

class UnretrievedURLException(MockHTTPExpectationFailure):
    """Raised when MockHTTP has not gotten a request for a URL that it needed to get a request for."""
    pass

class URLOrderingException(MockHTTPExpectationFailure):
    """Raised when MockHTTP got requests for URLs in the wrong order."""
    pass

class WrongBodyException(MockHTTPExpectationFailure):
    """Raised when MockHTTP got a request with the wrong body."""
    pass

class WrongHeaderException(MockHTTPExpectationFailure):
    """Raised when MockHTTP got a request with an invalid header."""
    pass

class Expectation(object):
    """A request that a MockHTTP server is expecting. Don't construct these
    directly, use :meth:`MockHTTP.expects`"""
    def __init__(self, mock, method, path, body=None, headers=None, times=None,
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
        self.failure = None
        self.name = name
        if name is not None:
            self.mock.expected_by_name[name] = self
        if after is not None:
            self.after = self.mock.expected_by_name[after]
        else:
            self.after = None
    
    def will(self, http_code=None, headers=None, body=None):
        """Specifies what to do in response to a matching request.
        
        :param http_code: The HTTP code to send. *Default:* 200 OK.
        :param headers: The HTTP headers to send, specified as a dictionary\
        mapping header to value. *Default:* No headers are sent.
        :param body: A string object containing the HTTP body to send. To send\
        unicode, first encode it to utf-8. (And probably include an appropriate\
        content-type header.) *Default:* No body is sent.
        :returns: This :class:`Expectation` object."""
        if http_code is not None:
            self.response_code = http_code
        if body is not None:
            self.response_body = body
        if headers is not None:
            self.response_headers = headers
        return self
    
    def check(self, method, path, headers, body):
        """Check this Expectation against the given request."""
        try:
            self._check_headers(method, path, headers)
            self._check_body(method, path, body)
            self._check_times(method, path)
            self._check_order(method, path)
            return True
        except MockHTTPExpectationFailure, e:
            self.failure = e
            raise
    
    def _check_headers(self, method, path, headers):
        if self.request_headers:
            for header, value in self.request_headers.iteritems():
                if header not in headers:
                    raise WrongHeaderException(
                        'Expected header missing on %s %s: %s' %\
                        (method, path, header))
                elif headers[header] != value:
                    raise WrongHeaderException(
                        'Wrong value for %s on %s %s. Expected: %r Got: %r' %\
                        (header, method, path, headers[header], value))
    
    def _check_body(self, method, path, body):
        if self.request_body is not None and body != self.request_body:
            self.mock.wrong_body = True
            raise WrongBodyException(
                '%s %s: Expected request body %r Got: %r' %\
                (method, path, self.request_body, body))
    
    def _check_times(self, method, path):
        if self.times is never:
            raise UnexpectedURLException('%s %s, expected never' %\
                                         (method, path))
        elif self.times is once and self.invoked:
            raise AlreadyRetrievedURLException('%s %s twice, expected once' %\
                                               (method, path))
    
    def _check_order(self, method, path):
        if self.after is not None and not self.after.invoked:
            self.mock.out_of_order = True
            raise URLOrderingException('%s %s expected only after %s %s' %
                                       (method, path,
                                        self.after.method, self.after.path))
    
    def respond(self, request):
        """Respond to a request."""
        request.send_response(self.response_code)
        for header, value in self.response_headers.iteritems():
            request.send_header(header, value)
        request.end_headers()
        request.wfile.write(self.response_body)
        self.invoked = True

class MockHTTP(object):
    """A Mock HTTP Server for unit testing web services calls.
    
    Basic Usage::
    
         mock_server = MockHTTP(42424)
         mock_server.expects(GET, '/index.html').will(body='A HTML body.')
         mock_server.expects(GET, '/asdf').will(http_code=404)
         urlopen('http://localhost:42424/index.html').read() == 'A HTML body.'
         urlopen('http://localhost:42424/asdf') # HTTPError: 404
         mock_server.verify()"""
    
    def __init__(self, port):
        """Create a MockHTTP server listening on localhost at the given port."""
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
        self.last_failure = None
        self.expected = defaultdict(dict)
        self.expected_by_name = {}
    
    def expects(self, method, path, *args, **kwargs):
        """Declares an HTTP Request that this MockHTTP expects.
        
        :param method: The HTTP method expected to use to access this URL.
        :param path: The expected path segment of this URL.
        :param body: The expected contents of the request body, as a string. If\
        you expect to send unicode, encode it as utf-8 first. *Default:* The\
        contents of the request body are irrelevant.
        :param headers: Expected headers as a dictionary mapping header name to\
        expected value. Checks to make sure that all expected headers are\
        present and have the specified values. *Default:* No headers are\
        required.
        :param times: The number of times this URL expects to be requested. Use\
        mock_http.never, mock_http.once, or mock_http.at_least_once for this.\
        *Default:* It does not matter how many times the URL is accessed.
        :param name: A name that can be used to refer to this expectation later.\
        *Default:* The expectation has no name.
        :param after: This URL must be accessed after a previously-named URL.\
        *Default:* The URL can be accessed at any time.
        :returns: The :class:`Expectation` object describing how this URL is\
        expected. You'll probably want to call :meth:`Expectation.will` on it\
        to describe how the URL should be responded to.
        """
        expectation = Expectation(self, method, path, *args, **kwargs)
        self.expected[method][path] = expectation
        return expectation
    
    def verify(self):
        """Close down the server and verify that this MockHTTP has met all its
        expectations.
        
        :returns: True, if all went as expected.
        :raises MockHTTPExpectationFailure: Or a subclass, describing the last\
        unexpected thing that happened."""
        self.finish_serving.set()
        self.finished_serving.wait()
        if self.last_failure is not None:
            raise self.last_failure
        for method, expected in self.expected.iteritems():
            for path, expectation in expected.iteritems():
                if (expectation.times is once or\
                    expectation.times is at_least_once) and\
                   not expectation.invoked:
                    raise UnretrievedURLException("%s not %s" % (path, method))
        return True
    
    def is_expected(self, method, path, headers, body):
        """Test to see whether a request is expected.
        
        .. todo::
            Gracefully handle multiple expectations for the same URL and method.
        
        :raises MockHTTPExpectationFailure: Or a subclass, describing why this\
        request is unexpected.
        :returns: The :class:`Expectation` object that expects this request."""
        try:
            if path not in self.expected[method]:
                raise UnexpectedURLException('Unexpected URL: %s' % path)
            expectation = self.expected[method][path]
            if expectation.check(method, path, headers, body):
                return expectation
        except MockHTTPExpectationFailure, failure:
            self.last_failure = failure
            raise

class RequestHandler(BaseHTTPServer.BaseHTTPRequestHandler, object):
    """Used by :class:`MockHTTP` to process requests."""
    
    rbufsize = 0
    
    def __init__(self, mock, *args, **kwargs):
        """Needs to be initialized with a MockHTTP object in addition to normal
        parameters to a :class:`BaseHTTPServer.BaseHTTPRequestHandler`."""
        self.mock = mock
        super(RequestHandler, self).__init__(*args, **kwargs)
    
    def __getattr__(self, name):
        """Fancy __getattr__ magic to permit arbitrary do_* methods."""
        if name.startswith('do_'):
            method = name[3:]
            return lambda: self.do(method)
    
    def fail(self, message=None):
        """Standardized mechanism for reporting failure."""
        self.mock.failed_url = self.path
        self.send_response(404, message)
        self.end_headers()
        self.wfile.write('')
    
    def do(self, method):
        """Process an HTTP request.
        
        :param method: The HTTP method used to make this request."""
        try:
            request_body = ''
            while select.select([self.rfile], [], [], 0.5)[0]:
                request_body += self.rfile.read(1)
            self.mock.is_expected(method, self.path, self.headers,
                                  request_body).respond(self)
        except MockHTTPExpectationFailure, failure:
            return self.fail(failure)
