:mod:`mock_http` -- Mock HTTP Module
====================================

.. automodule:: mock_http

Public Classes
--------------
.. autoclass:: MockHTTP
    :members:

.. autoclass:: Expectation
    :members:

Public Exceptions
-----------------
.. autoexception:: MockHTTPException

.. autoexception:: MockHTTPExpectationFailure

.. autoexception:: UnexpectedURLException

.. autoexception:: AlreadyRetrievedURLException

.. autoexception:: UnretrievedURLException

.. autoexception:: URLOrderingException

.. autoexception:: WrongBodyException

.. autoexception:: WrongHeaderException

.. autoexception:: WrongHeaderValueException

Private Classes
---------------
.. autoclass:: TimeoutHTTPServer
    :members:

.. autoclass:: RequestHandler
    :members:

Private Functions
-----------------
.. autofunction:: _server_thread
