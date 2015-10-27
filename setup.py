#!/usr/bin/env python

from setuptools import setup


setup(
	name='dawn',
	version='0.1.1',
	description='Open and modify ePubs',
	author='Arthur Darcet',
	author_email='hello+dawn@glose.com',
	url='http://github.com/Glose/dawn',
	license='MIT',
	packages=['dawn'],
	install_requires=[
		'lxml>=3.4.0',
	],
	test_suite='test',
	classifiers=[
		'Development Status :: 4 - Beta',
		'Intended Audience :: Developers',
		'License :: OSI Approved :: MIT License',
		'Operating System :: OS Independent',
		'Programming Language :: Python',
		'Programming Language :: Python :: 3.3',
		'Programming Language :: Python :: 3.4',
		'Programming Language :: Python :: 3.5',
		'Topic :: Software Development :: Libraries :: Python Modules',
	],
)
