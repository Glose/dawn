import collections
import datetime
import mimetypes
import posixpath
import oset
import uuid
import zipfile

from lxml import etree
from lxml import builder


NS = {
	'container': 'urn:oasis:names:tc:opendocument:xmlns:container',
	'opf': 'http://www.idpf.org/2007/opf',
	'dc': 'http://purl.org/dc/elements/1.1/',
	'ncx': 'http://www.daisy.org/z3986/2005/ncx/',
}
RNS = {v: k for k, v in NS.items()}

def getxmlattr(tag, attr):
	if ':' in attr:
		ns, attr = attr.split(':', 1)
		return tag.get('{{{}}}{}'.format(NS[ns], attr))
	else:
		try:
			return tag.attrib[attr]
		except KeyError:
			qname = etree.QName(tag.tag)
			return tag.get('{{{}}}{}'.format(RNS[qname.namespace], attr))


def ns(name, default_ns=None):
	if ':' in name:
		ns, name = name.split(':', 1)
	else:
		ns = default_ns
	if ns is None:
		return name
	else:
		return '{{{}}}{}'.format(NS[ns], name)


class Epub(zipfile.ZipFile):
	_version = None
	
	def __init__(self, infile, mode='r', version=None, opf=None):
		super().__init__(infile, mode=mode)
		if version is not None:
			self.version = version
		self.opf = opf
		self.manifest = Manifest()
		self.spine = Spine()
		self.toc = Toc()
		self.meta = {}
		
		if self.mode == 'r':
			self.__init_read()
		elif self.mode == 'w':
			self.__init_write()
		else:
			raise TypeError('mode should be \'r\' or \'w\'')
	
	@property
	def version(self):
		return self._version
	@version.setter
	def version(self, value):
		self.__class__ = VERSIONS[value]
	
	def __exit__(self, *args):
		self._write()
		return super().__exit__(*args)
	
	def __init_read(self):
		if self.opf is not None:
			raise TypeError('Can\'t set the opfpath when opening in \'r\' mode')
		
		with self._open('META-INF/container.xml') as f:
			tree = etree.parse(f)
		self.opf = tree.find('./container:rootfiles/container:rootfile', NS).get('full-path')
		
		if self.version is None:
			with self._open(self.opf) as f:
				opftree = etree.parse(f).getroot()
			self.version = opftree.get('version')
		
		self._read(opftree)
		
		uid_id = opftree.get('unique-identifier')
		self.uid = next(filter(lambda i: i['id'] == uid_id, self.meta['identifiers']), None)
	
	def __init_write(self):
		if self.version is None:
			raise TypeError('Version is required when opening an ePub in \'w\' mode')
		
		if self.opf is None:
			self.opf = 'content.opf'
		self.uid = AttributedString(uuid.uuid4())
		self.uid['id'] = 'uid_id'
		self.uid['scheme'] = 'uuid'
		self.meta['identifiers'] = [self.uid]
		
		self._writestr('mimetype', b'application/epub+zip', compress_type=zipfile.ZIP_STORED)
		
		E = builder.ElementMaker(namespace=NS['container'], nsmap=NS)
		container = E.container(
			E.rootfiles(
				E.rootfile({
					'full-path': self.opf,
					'media-type': 'application/oebps-package+xml',
				}),
			),
		)
		self._writestr(
			'META-INF/container.xml',
			etree.tostring(container, pretty_print=True),
			compress_type=zipfile.ZIP_STORED,
		)
	
	def _read(self, opf):
		raise NotImplementedError
	
	def _write(self):
		raise NotImplementedError
	
	def write(self, *args, **kwargs):
		raise NotImplementedError('Use writestr')
	
	def _writestr(self, *args, **kwargs):
		super().writestr(*args, **kwargs)
	
	def writestr(self, item, data, iid=None, **kwargs):
		if isinstance(item, zipfile.ZipInfo):
			raise NotImplementedError('item should be a path relative to the opfdir or an Item')
		if not isinstance(item, self.manifest.Item):
			item = self.manifest.add(item)
		self._writestr(self.__opfpath(item.href), data, **kwargs)
		return item
	
	def _open(self, *args, **kwargs):
		return super().open(*args, **kwargs)
	
	def open(self, item, *args, **kwargs):
		if isinstance(item, self.manifest.Item):
			item = item.href
		return self._open(self.__opfpath(item), *args, **kwargs)
	
	def __opfpath(self, path):
		return posixpath.join(posixpath.dirname(self.opf), path)
	
	def __repr__(self):
		return '<Epub {} (len(manifest): {}, len(spine): {})>'.format(self.version, len(self.manifest), len(self.spine))


class Manifest(dict):
	class Item:
		def __init__(self, iid, href):
			self.iid = iid
			self.href = href
		
		@property
		def mimetype(self):
			if self.href.endswith('.html') or self.href.endswith('.htm'):
				return 'application/xhtml+xml'
			else:
				return mimetypes.guess_type(self.href)[0]
		
		def __hash__(self):
			return hash(self.iid)
	
	def add(self, item):
		key = 'item-{}'.format(len(self))
		self[key] = item
		return self[key]
	
	def __setitem__(self, k, v):
		if isinstance(v, str):
			v = self.Item(k, v)
		if not isinstance(v, self.Item):
			raise TypeError('The manifest needs to be a dict of Manifest.Item')
		super().__setitem__(k, v)
	
	def byhref(self, href):
		href = href.rsplit('#', 1)[0]
		return next(filter(lambda item: item.href == href, self.values()))


class Spine(oset.oset):
	def add(self, item):
		if not isinstance(item, Manifest.Item):
			raise TypeError('The spine needs to be an ordered set of Manifest.Item')
		return super().add(item)


class Toc(list):
	def __init__(self, *args, **kwargs):
		self.title = 'Table of contents'
	
	class Item:
		def __init__(self, href, title, children=None):
			self.href = href
			self.title = title
			self.children = children or Toc()
	
	def append(self, item, title=None, children=None):
		if isinstance(item, str):
			if title is None:
				raise TypeError('Need a title to add an href to the TOC')
			item = self.Item(item, title)
			for a in children or []:
				item.children.append(*a)
		if not isinstance(item, self.Item):
			raise TypeError('The TOC needs to be a list of Toc.Item')
		super().append(item)
		return item


class AttributedString(str):
	def __init__(self, *args, **kwargs):
		self.__data = {}
	
	def __getitem__(self, k):
		return self.__data[k]
	
	def __setitem__(self, k, v):
		self.__data[k] = v
	
	def __delitem__(self, k):
		del self.__data[k]
	
	def __repr__(self):
		return '<AttributedString {!r} {}>'.format(str(self), self.__data)


class Epub20(Epub):
	_version = '2.0'
	
	def _read_manifest(self, opf):
		for item in opf.findall('./opf:manifest/', NS):
			self.manifest[getxmlattr(item, 'id')] = getxmlattr(item, 'href')
	
	def _read_spine(self, opf):
		for item in opf.findall('./opf:spine/', NS):
			item = self.manifest[getxmlattr(item, 'idref')]
			self.spine.add(item)
	
	def _read_toc(self, opf):
		toc_id = getxmlattr(opf.find('./opf:spine', NS), 'toc')
		if not toc_id:
			return
		
		def parse(tag):
			for np in tag.findall('./ncx:navMap/ncx:navPoint', NS):
				self.toc.append(
					getxmlattr(np.find('./ncx:content', NS), 'src'),
					np.find('./ncx:navLabel/ncx:text', NS).text,
					parse(np),
				)
		
		with self.open(self.manifest[toc_id]) as f:
			ncx = etree.parse(f).getroot()
		
		parse(ncx)
		title_tag = ncx.find('./ncx:docTitle/ncx:text', NS)
		if title_tag is not None:
			self.title = title_tag.text
	
	__meta = [
		# tag, attributes, multiple
		('title', ('lang',), True),
		('creator', ('opf:role', 'opf:file-as'), True),
		('subject', (), True),
		('description', (), False),
		('publisher', (), False),
		('contributor', ('opf:role', 'opf:file-as'), True),
		('date', ('opf:event',), True),
		# Drop type
		# Drop format
		('identifier', ('id', 'opf:scheme'), True),
		('source', (), False),
		('language', (), True),
		# Drop relation
		# Drop coverage
		# Drop rights
	]
	
	def _read_meta(self, opf):
		metadata = opf.find('./opf:metadata', NS)
		def extract(tag, attrs):
			for item in metadata.findall('dc:' + tag, NS):
				res = AttributedString(item.text)
				for k in attrs:
					res[k.split(':', 1)[-1]] = getxmlattr(item, k)
				yield res
		for tag, attrs, multi in self.__meta:
			f = list if multi else lambda it: next(it, None)
			self.meta[tag + ('s' if multi else '')] = f(extract(tag, attrs))
	
	def _write_opf(self):
		Eopf = builder.ElementMaker(namespace=NS['opf'], nsmap=NS)
		Edc = builder.ElementMaker(namespace=NS['dc'], nsmap=NS)
		
		meta = Eopf.metadata(
			Edc.format('application/epub+zip'),
			Edc.date(
				datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
				{ns('opf:event'): 'publication'},
			),
		)
		for tag, attrs, multi in self.__meta:
			todo = self.meta.get(tag + ('s' if multi else ''))
			if not todo:
				continue
			if not multi:
				todo = [todo]
			for astr in todo:
				meta.append(getattr(Edc, tag)(
					str(astr),
					{ns(k): astr[k.split(':', 1)[-1]] for k in attrs},
				))
		
		package = Eopf.package(
			meta,
			Eopf.manifest(*(
				Eopf.item({
					'id': item.iid,
					'href': item.href,
					'media-type': item.mimetype,
				})
				for item in self.manifest.values()
			)),
			Eopf.spine(*(
				Eopf.itemref({'idref': item.iid})
				for item in self.spine
			)),
		)
		self._writestr(self.opf, etree.tostring(package, pretty_print=True))
	
	def _write_toc(self):
		E = builder.ElementMaker(namespace=NS['ncx'], nsmap=NS)
		
		def navmap(toc):
			for item in toc:
				yield E.navPoint(
					E.navLabel(E.text(item.title)),
					E.navMap(*(navmap(item.children))),
				)
		
		toc = E.ncx(
			{'version': '2005-1'},
			E.head(),
			E.docTitle(E.text(self.toc.title)),
			E.navMap(*navmap(self.toc)),
		)
		
		self.writestr('toc.ncx', etree.tostring(toc, pretty_print=True))
	
	def _read(self, opf):
		self._read_manifest(opf)
		self._read_spine(opf)
		self._read_toc(opf)
		self._read_meta(opf)
	
	def _write(self):
		self._write_toc()
		self._write_opf()


class Epub30(Epub):
	_version = '3.0'
	
	def __exit__(self, *args):
		raise NotImplementedError


VERSIONS = {e._version: e for e in (Epub20, Epub30)}
