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
	['2.0', 'eeed938231a3ba4c1ed154e7994919130f8e4146'],
	['3.0', 'a3e37e04c5929e94053b73cad9d5f71b7c2ec60a'],
])
def test_epub(version, expected):
	out = io.BytesIO()
	with dawn.open(out, mode='w', version=version) as epub:
		epub.meta['creators'] = [dawn.AS('Me', role='author')]
		epub.meta['description'] = dawn.AS('Awesome book')
		epub.meta['titles'] = [dawn.AS('My ePub', lang='en')]

		for href, title in [
			('README.md', 'README'),
			('dawn/__init__.py', 'dawn.py'),
		]:
			with open(href, 'r') as f:
				item = epub.writestr(href, f.read())
			epub.spine.append(item)
			epub.toc.append(href, title=title)

		epub.toc.append('main section', 'main title', [
			('sub href', 'sub title'),
			('sub href2', 'sub title2', [
				('sub sub href', 'sub sub title'),
			]),
		])

	dbg = '/tmp/epub{}.epub'.format(version)

	with open(dbg, 'wb') as f:
		f.write(out.getvalue())

	H = hashlib.sha1(out.getvalue()).hexdigest()
	assert H == expected, 'Debug file is at {}'.format(dbg)

	os.unlink(dbg)

def test_missing_version():
	with pytest.raises(TypeError):
		dawn.open(None, mode='w')


@pytest.fixture
def dummy():
	with dawn.open(io.BytesIO(), mode='w', version='2.0') as epub:
		yield epub

def test_write_method(dummy):
	with pytest.raises(NotImplementedError):
		dummy.write()

def test_writestr_zipinfo(dummy):
	with pytest.raises(NotImplementedError):
		dummy.writestr(zipfile.ZipInfo('path'), b'')

def test_manifest_wrong_type(dummy):
	with pytest.raises(TypeError):
		dummy.manifest['blih'] = None

def test_spine_wrong_type(dummy):
	with pytest.raises(TypeError):
		dummy.spine.append('blih')

def test_toc_add_missing_title(dummy):
	with pytest.raises(TypeError):
		dummy.toc.append('blih')

def test_toc_add_wrong_type(dummy):
	with pytest.raises(TypeError):
		dummy.toc.append(None)
