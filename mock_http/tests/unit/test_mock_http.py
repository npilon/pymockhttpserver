from unittest import TestCase
import urllib2
from mock_http import MockHTTP, UnexpectedURLException
from random import randint

class TestMockHTTP(TestCase):
    def setUp(self):
        self.server_port = randint(49152, 65535)
    
    def test_get_request(self):
        """Tests a get request that expects nothing to return but an 200."""
        mock = MockHTTP(self.server_port)
        mock.expects(path='/index.html')
        urllib2.urlopen('http://127.0.0.1:%s/index.html' % self.server_port)
        self.assert_(mock.verify())
    
    def test_get_request_wrong_url(self):
        """Tests a get request that expects a different URL."""
        mock = MockHTTP(self.server_port)
        mock.expects(path='/index.html')
        self.assertRaises(urllib2.HTTPError, urllib2.urlopen,
                          'http://127.0.0.1:%s/notindex.html' % self.server_port)
        self.assertRaises(UnexpectedURLException, mock.verify)
