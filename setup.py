from setuptools import setup, find_packages
import sys, os

version = '1.0'

setup(name='mock_http',
      version=version,
      description="A mock http server for unit testing code that uses web services.",
      long_description="""mock_http lets you start an HTTP server in a separate
      thread, tell it to respond to specific requests, make requests against it,
      shut it down cleanly, and verify that appropriate calls were made.""",
      classifiers=[
          'Development Status :: 5 - Production/Stable',
          'Intended Audience :: Developers',
          'License :: OSI Approved :: Apache Software License',
          'Operating System :: OS Independent',
          'Programming Language :: Python',
          'Topic :: Internet :: WWW/HTTP',
          'Topic :: Software Development :: Testing',
          'Topic :: Software Development :: Libraries :: Python Modules',
      ], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='',
      author='Nick Pilon',
      author_email='npilon@oreilly.com',
      url='https://github.com/oreillymedia/pymockhttpserver',
      license='Apache 2',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      zip_safe=False,
      test_suite='nose.collector',
      install_requires=[
          # -*- Extra requirements: -*-
          'cherrypy',
          'httplib2',
      ],
      entry_points="""
      # -*- Entry points: -*-
      """,
      )
