try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

config = {
    'author': 'quatrix',
    'author_email': 'evil.legacy.com',
    'version': "0.1.0",
    'install_requires': [],
    'packages': ['rate_limit'],
    'scripts': [],
    'name': 'rate_limit'
}

setup(**config)
