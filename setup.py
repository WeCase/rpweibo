import sys

if sys.version_info[0] < 3:
    sys.stderr.write("Python (<= 2) is not supported!\n")
    sys.exit(1)

import rpweibo

try:
    from setuptools import setup
    use_setuptools = True
except ImportError:
    from distutils.core import setup
    use_setuptools = False

kw = {
    "name": 'rpweibo',
    "version": rpweibo.__version__,
    "description": 'cURL + Python Weibo Wrapper',
    "long_description": open('README.md', 'r').read(),
    "author": 'Tom Li',
    "author_email": 'biergaizi@member.fsf.org',
    "url": 'https://github.com/WeCase/rpweibo',
    "download_url": 'https://github.com/WeCase/rpweibo',
    "license": 'LGPLv3+',
    "py_modules": ['rpweibo'],
    "requires": ["pycurl (>= 7.19.3)", "rsa (>=3.1)"],
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

if use_setuptools:
    requires = kw.pop("requires")
    for idx, val in enumerate(requires):
        requires[idx] = val.replace("(", "").replace(")", "")
    kw["install_requires"] = requires


setup(**kw)
