import datetime
import dawn
import io
import hashlib
import os
import pytest
import unittest.mock
import zipfile


@pytest.fixture
def reproductible():
	orig = zipfile.ZipFile.writestr
	def writestr(self, path, *args, **kwargs):
		if isinstance(path, str):
			# this makes path a zipinfo with a datetime of 1980-01-01
			path = zipfile.ZipInfo(path)
		return orig(self, path, *args, **kwargs)

	now = datetime.datetime(2019, 7, 31)
	with \
		unittest.mock.patch('datetime.datetime') as dt, \
		unittest.mock.patch('uuid.uuid4', return_value='mocked uuid'), \
		unittest.mock.patch.object(zipfile.ZipFile, 'writestr', writestr):
		dt.now.return_value = now
		yield

pytestmark = pytest.mark.usefixtures('reproductible')

@pytest.mark.parametrize('version,expected', [
	['2.0', '8e10b17d7905b1586ead9cf846eb0fc10fcc56a9'],
	['3.0', 'b88d39831425c40bf248356bc0eaaf55bb431099'],
])
def test_epub(version, expected):
	out = io.BytesIO()
	with dawn.open(out, mode='w', version=version) as epub:
		epub.meta['creators'] = [dawn.AS('Me', role='author')]
		epub.meta['description'] = dawn.AS('Awesome book')
		epub.meta['title'] = dawn.AS('My ePub', lang='en')

		for href, title in [
			('README.md', 'README'),
			('dawn/__init__.py', 'dawn.py'),
		]:
			with open(href, 'r') as f:
				item = epub.writestr(href, f.read())
			epub.spine.append(item)
			epub.toc.append(href, title=title)

	dbg = '/tmp/epub{}.epub'.format(version)

	with open(dbg, 'wb') as f:
		f.write(out.getvalue())

	H = hashlib.sha1(out.getvalue()).hexdigest()
	assert H == expected, 'Debug file is at {}'.format(dbg)

	os.unlink(dbg)

def test_missing_version():
	with pytest.raises(TypeError):
		dawn.open(None, mode='w')
