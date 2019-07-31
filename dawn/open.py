import lxml.etree
import zipfile

from .epub import VERSIONS
from .utils import NS


class open:
	def __init__(self, infile, mode='r', version=None, opfpath=None):
		if mode not in ('r', 'w'):
			raise TypeError('Supported modes are r, w and a')
		if mode == 'r' and opfpath is not None:
			raise TypeError('opfpath should only be used in w mode')
		if mode == 'w' and version is None:
			raise TypeError('version is required in w mode')

		self._mode = mode
		self._opfpath = opfpath
		self._version = version
		self._zf = zipfile.ZipFile(infile, mode=mode)

	def __enter__(self):
		self._zf.__enter__()

		if self._mode == 'r':
			with self._zf.open('META-INF/container.xml') as f:
				tree = lxml.etree.parse(f)

			opfpath = tree.find('./container:rootfiles/container:rootfile', NS).get('full-path')

			with self._zf.open(opfpath) as f:
				opftree = lxml.etree.parse(f).getroot()

			version = self._version or opftree.get('version')

			self._epub = VERSIONS[version](self._zf, opfpath)
			self._epub._init_read(opftree)

		else:
			assert self._mode == 'w'
			opfpath = self._opfpath or 'content.opf'
			self._epub = VERSIONS[self._version](self._zf, opfpath)
			self._epub._init_write()

		return self._epub

	def __exit__(self, *args):
		if self._mode == 'w':
			self._epub._write_opf()
		self._zf.__exit__(*args)
		del self._epub
		del self._zf
