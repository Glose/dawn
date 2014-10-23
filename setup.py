#!/usr/bin/env python

from setuptools import setup


setup(
	name='dawn',
	version='0.0.1',
	description='Open and modify ePubs',
	author='Arthur Darcet',
	author_email='hello+dawn@glose.com',
	url='http://github.com/Glose/dawn',
	packages=['dawn'],
	test_suite='test',
	classifiers=[
		'Development Status :: 4 - Beta',
		'Intended Audience :: Developers',
		'Programming Language :: Python :: 3.3',
		'Topic :: Software Development :: Libraries :: Python Modules',
	],
)