import abc
import collections
import datetime
import lxml.etree
import lxml.builder
import mimetypes
import posixpath
import re
import sys
import uuid
import zipfile


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

			self._epub = _Epub._versions[version](self._zf, opfpath)
			self._epub._init_read(opftree)

		else:
			assert self._mode == 'w'
			opfpath = self._opfpath or 'content.opf'
			self._epub = _Epub._versions[self._version](self._zf, opfpath)
			self._epub._init_write()

		return self._epub

	def __exit__(self, *args):
		if self._mode == 'w':
			self._epub._write_opf()
		self._zf.__exit__(*args)
		del self._epub
		del self._zf


class _Epub(abc.ABC):
	version = None
	_versions = {}

	def __init_subclass__(cls, *args, **kwargs):
		super().__init_subclass__(*args, **kwargs)
		cls._versions[cls.version] = cls

	def __init__(self, zf, opfpath):
		self._opfpath = opfpath
		self._zf = zf

		self.manifest = Manifest()
		self.spine = Spine()
		self.toc = Toc()
		self.meta = {
			'contributors': [], # list of AS with role and file-as
			'creators': [], # list of AS with role and file-as
			'dates': {'creation': None, 'publication': None, 'modification': None},
			'description': None, # AS with lang
			'identifiers': [], # list of AS with id and scheme
			'publisher': None, # AS with lang
			'languages': [],
			'source': None,
			'subjects': [],
			'titles': [], # list of AS with lang
		}

	def _init_read(self, opftree):
		self._read_manifest(opftree)
		self._read_spine(opftree)
		self._read_toc(opftree)
		self._read_meta(opftree)

		uid_id = opftree.get('unique-identifier')
		self.uid = next(filter(lambda i: i.get('id') == uid_id, self.meta['identifiers']), None)

	def _init_write(self):
		self.uid = AttributedString(uuid.uuid4())
		self.uid['id'] = 'uid_id'
		self.uid['scheme'] = 'uuid'
		self.meta['identifiers'] = [self.uid]

		self._writestr('mimetype', b'application/epub+zip', compress_type=zipfile.ZIP_STORED)

		container = E['container'].container(
			E['container'].rootfiles(
				E['container'].rootfile({
					'full-path': self._opfpath,
					'media-type': 'application/oebps-package+xml',
				}),
			),
		)
		self._writestr(
			'META-INF/container.xml',
			lxml.etree.tostring(container, pretty_print=True),
			compress_type=zipfile.ZIP_STORED,
		)

	def _write_opf(self):
		self.meta['dates']['modification'] = datetime.datetime.now()

		if self._toc_item is not None:
			self._write_toc()
		pkg = E['opf'].package(
			{'version': self.version, 'unique-identifier': self.uid['id']},
			self._xml_meta(),
			self._xml_manifest(),
			self._xml_spine(),
		)
		self._writestr(self._opfpath, lxml.etree.tostring(pkg, pretty_print=True))

	@abc.abstractmethod
	def _read_toc(self, opftree): # pragma: no cover
		...

	@abc.abstractmethod
	def _read_meta(self, opftree): # pragma: no cover
		...

	def _read_manifest(self, opftree):
		for item in opftree.findall('./opf:manifest/opf:item', NS):
			self.manifest[getxmlattr(item, 'id')] = getxmlattr(item, 'href')

	def _read_spine(self, opftree):
		for item in opftree.findall('./opf:spine/opf:itemref', NS):
			item = self.manifest[getxmlattr(item, 'idref')]
			self.spine.append(item)

	@abc.abstractmethod
	def _write_toc(self): # pragma: no cover
		...

	def _xml_meta(self):
		return E['opf'].metadata(E['dc'].format('application/epub+zip'))

	def _xml_manifest(self):
		return E['opf'].manifest(*(
			E['opf'].item({
				'id': item.iid,
				'href': item.href,
				'media-type': item.mimetype,
			})
			for item in self.manifest.values()
		))

	def _xml_spine(self):
		return E['opf'].spine(*(
			E['opf'].itemref({'idref': item.iid})
			for item in self.spine
		))

	def write(self, *args, **kwargs):
		raise NotImplementedError('Use writestr')

	def _writestr(self, *args, **kwargs):
		self._zf.writestr(*args, **kwargs)

	def writestr(self, item, data, iid=None, **kwargs):
		if isinstance(item, zipfile.ZipInfo):
			raise NotImplementedError('item should be a path relative to the opfdir or an Item')
		if not isinstance(item, self.manifest.Item) or item.iid not in self.manifest:
			item = self.manifest.add(item)
		self._writestr(self.__opfpath(item.href), data, **kwargs)
		return item

	def open(self, item, *args, **kwargs):
		if isinstance(item, self.manifest.Item):
			item = item.href
		return self._zf.open(self.__opfpath(item), *args, **kwargs)

	def __opfpath(self, path):
		return posixpath.join(posixpath.dirname(self._opfpath), path)

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

		def __repr__(self):
			return '<Manifest.Item {}>'.format(self.__dict__)

	def add(self, item):
		if not isinstance(item, self.Item):
			item = self.Item('item-{}'.format(len(self)), item)
		self[item.iid] = item
		return item

	def __setitem__(self, k, v):
		if isinstance(v, str):
			v = self.Item(k, v)
		if not isinstance(v, self.Item):
			raise TypeError('The manifest needs to be a dict of Manifest.Item')
		super().__setitem__(k, v)

	def byhref(self, href):
		href = href.split('#', 1)[0]
		it = filter(lambda item: item.href == href, self.values())
		try: return next(it)
		except StopIteration: raise KeyError(href)


class Spine(list):
	def append(self, item):
		if not isinstance(item, Manifest.Item):
			raise TypeError('The spine needs to be a list of Manifest.Item')
		return super().append(item)


class Toc(list):
	class Item:
		def __init__(self, href, title):
			self.href = href
			self.title = title
			self.children = Toc()

		def __repr__(self):
			return '<Toc.Item {}>'.format(self.__dict__)

	def __init__(self):
		self.title = None

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


class AttributedString(collections.UserDict, str):
	def __new__(cls, value, **kwargs):
		return super().__new__(cls, value)

	def __init__(self, value, **kwargs):
		self.data = kwargs

	def __repr__(self):
		return '<AttributedString {!r} {}>'.format(str(self), self.data)
AS = AttributedString


class Epub20(_Epub):
	version = '2.0'

	def _read_toc(self, opftree):
		toc_id = getxmlattr(opftree.find('./opf:spine', NS), 'toc')
		if toc_id is None:
			return

		def parse(tag):
			for np in tag.findall('./ncx:navMap/ncx:navPoint', NS):
				yield (
					getxmlattr(np.find('./ncx:content', NS), 'src'),
					np.find('./ncx:navLabel/ncx:text', NS).text,
					parse(np),
				)

		self._toc_item = self.manifest.pop(toc_id)
		with self.open(self._toc_item) as f:
			ncx = lxml.etree.parse(f).getroot()

		for a in parse(ncx):
			self.toc.append(*a)

		title_tag = ncx.find('./ncx:docTitle/ncx:text', NS)
		if title_tag is not None:
			self.toc.title = title_tag.text

	__meta = [
		# tag, attributes, multiple
		('title', ('lang',), True),
		('creator', ('opf:role', 'opf:file-as'), True),
		('subject', (), True),
		('description', (), False),
		('publisher', (), False),
		('contributor', ('opf:role', 'opf:file-as'), True),
		# Drop type
		# Drop format
		# date handled manually
		('identifier', ('id', 'opf:scheme'), True),
		('source', (), False),
		('language', (), True),
		# Drop relation
		# Drop coverage
		# Drop rights
	]
	def _read_meta(self, opftree):
		metadata = opftree.find('./opf:metadata', NS)
		def extract(tag, attrs):
			for t in metadata.findall('dc:' + tag, NS):
				yield AttributedString(t.text, **{
					k.split(':', 1)[-1]: getxmlattr(t, k)
					for k in attrs
					if getxmlattr(t, k) is not None
				})

		for tag, attrs, multi in self.__meta:
			f = list if multi else lambda d: next(d, None)
			self.meta[tag + ('s' if multi else '')] = f(extract(tag, attrs))

		for astr in extract('date', ('opf:event',)):
			if astr['event'] in self.meta['dates']:
				self.meta['dates'][astr['event']] = parse_date(astr)

	def _xml_meta(self):
		meta = super()._xml_meta()

		for k, v in self.meta['dates'].items():
			if v is not None:
				meta.append(E['dc'].date(
					v.strftime('%Y-%m-%dT%H:%M:%SZ'),
					{ns('opf:event'): k},
				))

		for tag, attrs, multi in self.__meta:
			todo = self.meta.get(tag + ('s' if multi else ''))
			if not todo:
				continue
			if not multi:
				todo = [todo]
			for astr in todo:
				meta.append(getattr(E['dc'], tag)(
					str(astr),
					{ns(k): astr[k.split(':', 1)[-1]] for k in attrs},
				))

		return meta

	def _xml_manifest(self):
		if self.toc.item is not None:
			self.manifest.add(self.toc.item)
		res = super()._xml_manifest()
		if self.toc.item is not None:
			del self.manifest[self.toc.item.iid]
		return res

	def _xml_spine(self):
		spine = super()._xml_spine()
		if self._toc_item is not None:
			spine.attrib['toc'] = self._toc_item.iid

	def _write_toc(self):
		def navmap(toc):
			for item in toc:
				yield E['ncx'].navPoint(
					E['ncx'].navLabel(E['ncx'].text(item.title)),
					E['ncx'].navMap(*(navmap(item.children))),
				)

		toc = E['ncx'].ncx(
			{'version': '2005-1'},
			E['ncx'].head(),
			E['ncx'].docTitle(E['ncx'].text(self.toc.title or 'Table of contents')),
			E['ncx'].navMap(*navmap(self.toc)),
		)

		self.writestr(self._toc_item, lxml.etree.tostring(toc, pretty_print=True))


class Epub30(_Epub):
	version = '3.0'

	def _read_toc(self, opftree):
		toc_id = opftree.find('./opf:metadata/opf:item[@properties="nav"]', NS)
		if toc_id is None:
			return

		def parse(tag):
			for li in tag.findall('./html:ol/html:li/html:a', NS):
				a = li.find('./html:a', NS)
				yield (getxmlattr(a, 'href'), a.text, parse(np))

		self._toc_item = self.manifest.pop(toc_id)
		with self.open(self.toc.item) as f:
			toc = lxml.etree.parse(f).getroot()

		for a in parse(toc.find('.//html:nav[@ops:type="toc"]', NS)):
			self.toc.append(*a)

		title_tag = toc.find('.//html:h1', NS)
		if title_tag is not None:
			self.toc.title = title_tag.text

	__meta = [
		# tag, attributes, refine attribute map, multiple
		('identifier', (), True), # manually map identifier-type to scheme
		('title', ('lang',), True),
		('language', (), True),
		('contributor', (), True),
		# Drop coverage
		('creator', (), True),
		# manually handle dates
		('description', ('lang',), False),
		# Drop format
		('publisher', ('lang',), False),
		# Drop relation
		# Drop rights
		('source', (), False),
		('subject', (), True),
		# Drop type
	]
	__dates = [
		('created', 'creation'),
		('date', 'publication'),
		('modified', 'modification'),
	]
	def _read_meta(self, opftree):
		metadata = opftree.find('./opf:metadata', NS)

		def extract(tag, attrs):
			for t in metadata.findall('dc:' + tag, NS):
				res = AttributedString(t.text, **{
					k.split(':', 1)[-1]: getxmlattr(t, k)
					for k in attrs
					if getxmlattr(t, k) is not None
				})
				if getxmlattr(t, 'id') is not None:
					res['id'] = getxmlattr(t, 'id')
					for refine in metadata.findall('meta/[@refine="#{}"]'.format(res['id'])):
						res[getxmlattr(refine, 'property')] = refine.text
				yield res

		for tag, attrs, multi in self.__meta:
			f = list if multi else lambda it: next(it, None)
			self.meta[tag + ('s' if multi else '')] = f(extract(tag, attrs))

		for identifier in self.meta['identifiers']:
			if 'identifier-type' in identifier:
				identifier['scheme'] = identifier.pop('identifier-type')

		for tag, k in self.__dates:
			date = metadata.find('dc:' + tag, NS)
			if date is not None:
				self.meta['dates'][k] = parse_date(date.text)

	def _xml_meta(self):
		meta = super()._xml_meta()

		for k, v in self.meta['dates'].items():
			if v is not None:
				meta.append(E['dc'].date(
					v.strftime('%Y-%m-%dT%H:%M:%SZ'),
					{ns('opf:event'): k},
				))

		for tag, attrs, multi in self.__meta:
			todo = self.meta.get(tag + ('s' if multi else ''))
			if not todo:
				continue
			if not multi:
				todo = [todo]
			for astr in todo:
				meta.append(getattr(E['dc'], tag)(
					str(astr),
					# TODO
					{ns(k): astr[k.split(':', 1)[-1]] for k in attrs},
				))

		return meta

	def _xml_manifest(self):
		manifest = super()._xml_manifest()
		if self.toc.item is not None:
			manifest.append(E['opf'].item({
				'id': self.toc.item.iid,
				'href': self.toc.item.href,
				'media-type': self.toc.item.mimetype,
				'properties': 'nav',
			}))
		return manifest

	def _write_toc(self):
		if not re.search(r'^.+\.html?', self.toc.item.href):
			self.toc.item.href = '{}.{}'.format(self.toc.item.href.rsplit('.', 1)[0], 'html')

		def ol(toc):
			for item in toc:
				yield E['html'].ol(
					E['html'].a(item.title, {'href': item.href}),
					E['html'].ol(*(ol(item.children))),
				)

		toc = E['html'].html(
			{'version': '2005-1'},
			E['html'].head(),
			E['html'].h1(self.toc.title),
			E['html'].ol(*ol(self.toc)),
		)

		self._writestr('toc.html', lxml.etree.tostring(toc, pretty_print=True, method='html'))


NS = {
	'container': 'urn:oasis:names:tc:opendocument:xmlns:container',
	'opf': 'http://www.idpf.org/2007/opf',
	'ops': 'http://www.idpf.org/2007/ops',
	'dc': 'http://purl.org/dc/elements/1.1/',
	'ncx': 'http://www.daisy.org/z3986/2005/ncx/',
	'html': 'http://www.w3.org/1999/xhtml',
}

RNS = {v: k for k, v in NS.items()}

E = {k: lxml.builder.ElementMaker(namespace=v, nsmap=NS) for k, v in NS.items()}

def getxmlattr(tag, attr):
	if ':' in attr:
		ns, attr = attr.split(':', 1)
		return tag.get('{' + NS[ns] + '}' + attr)
	else:
		try:
			return tag.attrib[attr]
		except KeyError:
			qname = lxml.etree.QName(tag.tag)
			return tag.get('{' + RNS[qname.namespace] + '}' + attr)

def ns(name):
	if ':' in name:
		ns, name = name.split(':', 1)
		return '{' + NS[ns] + '}' + name
	else:
		return name

def parse_date(d):
	for p, l in (
		('%Y-%m-%dT%H:%M:%SZ', 20),
		('%Y-%m-%d', 10),
		('%Y-%m', 7),
		('%Y', 4),
	):
		if len(d) == l:
			return datetime.datetime.strptime(d, p)
