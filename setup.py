import os
from setuptools import setup

# Utility function to read the README file.
# Used for the long_description.  It's nice, because now 1) we have a top level
# README file and 2) it's easier to type in the README file than to put a raw
# string in below ...
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(
    name = "autodse",
    version = "0.0.1",
    author = "David Chen",
    author_email = "davidchencsl@gmail.com",
    description = ("A python library for automating DSE (Design Space Exploration)."),
    license = "BSD",
    keywords = "DSE library automation",
    url = "https://dse.davidchen.page",
    packages=['autodse'],
    long_description=read('README'),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Topic :: Utilities",
        "License :: OSI Approved :: BSD License",
    ],
    install_requires=read("requirements.txt").splitlines()
)