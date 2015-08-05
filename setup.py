import sys

if sys.version_info[0] < 3:
    sys.stderr.write("Python (<= 2) is not supported!\n")
    sys.exit(1)

import rpweibo
from distutils.core import setup

kw = {
    "name": 'rpweibo',
    "version": rpweibo.__version__,
    "description": 'cURL + Python Weibo Wrapper',
    "long_description": open('README.md', 'r').read(),
    "author": 'Tom Li',
    "author_email": 'biergaizi@member.fsf.org',
    "url": 'https://github.com/WeCase/rpweibo',
    "download_url": 'https://github.com/WeCase/rpweibo',
    "py_modules": ['rpweibo'],
    "requires": ["rsa (>=3.1)"],
    "classifiers": [
        'Development Status :: 3 - Alpha',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: Internet',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ]
}


setup(**kw)
