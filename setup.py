#!/usr/bin/env python

from setuptools import setup


requirements = [
	'lxml >= 4.3.4, < 5',
]

setup(
	name='dawn',
	version='0.2.0',
	description='Open and modify ePubs',
	author='Arthur Darcet',
	author_email='hello+dawn@glose.com',
	url='http://git.glose.com/opensource/dawn',
	license='MIT',
	packages=['dawn'],
	install_requires=requirements,
	setup_requires=[
		'pytest-runner >= 5.1, < 6',
	],
	tests_require=requirements + [
		'pytest',
		'pytest-cov',
	],
	test_suite='test',
	classifiers=[
		'Development Status :: 4 - Beta',
		'Intended Audience :: Developers',
		'License :: OSI Approved :: MIT License',
		'Operating System :: OS Independent',
		'Programming Language :: Python',
		'Programming Language :: Python :: 3.6',
		'Programming Language :: Python :: 3.7',
		'Topic :: Software Development :: Libraries :: Python Modules',
	],
)
