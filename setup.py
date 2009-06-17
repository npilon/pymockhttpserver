from setuptools import setup, find_packages
import sys, os

version = '0.1'

setup(name='mock_http',
      version=version,
      description="A mock http server for unit testing code that uses web services.",
      long_description="""\
""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='',
      author='Nick Pilon',
      author_email='npilon@oreilly.com',
      url='',
      license='',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      zip_safe=False,
      install_requires=[
          # -*- Extra requirements: -*-
      ],
      entry_points="""
      # -*- Entry points: -*-
      """,
      )
