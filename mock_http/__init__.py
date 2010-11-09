#!/usr/bin/env python
# Copyright 2010 O'Reilly Media, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Build a mock HTTP server that really works to unit test web service-dependent programs."""

#import BaseHTTPServer
from collections import defaultdict
import copy
import select
import socket
import time
import threading

from cherrypy.wsgiserver import CherryPyWSGIServer
from cherrypy._cptree import Tree
from cherrypy import request, response

__all__ = ['GET', 'POST', 'PUT', 'DELETE', 'never', 'once', 'at_least_once',
           'MockHTTP']

GET = 'GET'
POST = 'POST'
PUT = 'PUT'
DELETE = 'DELETE'

never = object()
once = object()
at_least_once = object()

def _server_thread(server, finished_serving):
    """Handle requests to our server in another thread."""
    server.start()
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

class WrongHeaderValueException(MockHTTPExpectationFailure):
    """Raised when MockHTTP got a request with an invalid header value."""
    pass

class WrongParamException(MockHTTPExpectationFailure):
    """Raised when MockHTTP got a request with an invalid param."""
    pass

class WrongParamValueException(MockHTTPExpectationFailure):
    """Raised when MockHTTP got a request with an invalid param value."""
    pass

class Expectation(object):
    """A request that a MockHTTP server is expecting. Don't construct these
    directly, use :meth:`MockHTTP.expects`"""
    def __init__(self, mock, method, path, body=None, headers=None, times=None,
                 name=None, after=None, params=None):
        self.mock = mock
        self.method = method
        self.path = path
        self.request_body = body
        # Ensure that nothing else can modify these after the mock is created.
        self.request_params = copy.copy(params)
        self.request_headers = copy.copy(headers)
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
    
    def check(self, method, path, params, headers, body):
        """Check this Expectation against the given request."""
        try:
            self._check_headers(method, path, headers)
            self._check_params(method, path, params)
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
                    raise WrongHeaderValueException(
                        'Wrong value for %s on %s %s. Expected: %r Got: %r' %\
                        (header, method, path, value, headers[header]))
    
    def _check_params(self, method, path, params):
        if self.request_params:
            for param, value in self.request_params.iteritems():
                if param not in params:
                    raise WrongParamException(
                        'Expected param missing on %s %s: %s' %\
                        (method, path, param))
                elif params[param] != value:
                    raise WrongParamValueException(
                        'Wrong value for %s on %s %s. Expected: %r Got: %r' %\
                        (param, method, path, value, params[param]))
    
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
    
    def respond(self):
        """Respond to a request."""
        response.status = self.response_code
        for header, value in self.response_headers.iteritems():
            response.headers[header] = value
        self.invoked = True
        return self.response_body

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
        self.server_address = ('localhost', port)
        self.finish_serving = threading.Event()
        self.finished_serving = threading.Event()
        tree = Tree()
        mock_root = MockRoot(self)
        tree.mount(mock_root, '/')
        self.server = CherryPyWSGIServer(
            self.server_address, tree, server_name='localhost', numthreads=1)
        self.thread = threading.Thread(
            target=_server_thread, kwargs={'server': self.server,
                                           'finished_serving': self.finished_serving})
        self.thread.start()
        while not self.server.ready:
            time.sleep(0.1)
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
        :param params: Expected query parameters as a dictionary mapping query\
        parameter name to expected value. Checks to make sure that all expected\
        query parameters are present and have specified values. *Default:* No\
        query parameters are expected.
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
        self.server.stop()
        self.finished_serving.wait()
        self.thread.join()
        if self.last_failure is not None:
            raise self.last_failure
        for method, expected in self.expected.iteritems():
            for path, expectation in expected.iteritems():
                if (expectation.times is once or\
                    expectation.times is at_least_once) and\
                   not expectation.invoked:
                    raise UnretrievedURLException("%s not %s" % (path, method))
        return True
    
    def is_expected(self, method, path, params, headers, body):
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
            if expectation.check(method, path, params, headers, body):
                return expectation
        except MockHTTPExpectationFailure, failure:
            self.last_failure = failure
            raise

def mock_fail(mock, path, message=None):
    """Standardized mechanism for reporting failure."""
    mock.failed_url = path
    response.status = '404 %s' % message
    return '404 %s' % message

class MockRoot(object):
    def __init__(self, mock):
        self.mock = mock
    
    def default(self, *args, **params):
        path = '/' + '/'.join(args)
        try:
            if request.body:
                body = request.body.read()
            else:
                body = ''
            return self.mock.is_expected(request.method, path, params,
                                         request.headers, body).respond()
        except MockHTTPException, failure:
            return mock_fail(self.mock, path, failure)
        except MockHTTPExpectationFailure, failure:
            return mock_fail(self.mock, path, failure)
    default.exposed = True
