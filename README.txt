mock_http
---------

mock_http is a python package for unit testing code that depends on web
services. It allows you to mock up the web service used by your software without
monkey-patching or modifying the code being tested. The mocked web service can
respond to specific requests with specific responses.

Installation
------------

mock_http is a setuptools package distributed through the Python Package Index.

To install from pypi:

easy_install mock_http

Usage
-----

from unittest import TestCase
import httplib2

mock = MockHTTP(self.server_port)
mock.expects(method=GET, path='/index.html')
resp, status = self.http.request(
    uri = 'http://localhost:%s/index.html' % self.server_port)
assert resp['status'] == '200'
assert mock.verify()