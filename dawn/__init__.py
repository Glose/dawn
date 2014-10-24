import collections
import datetime
import mimetypes
import posixpath
import re
import uuid
import zipfile

from lxml import etree
from lxml import builder


class Epub(zipfile.ZipFile):
	_version = None
	@property
	def version(self):
		return self._version
	@version.setter
	def version(self, value):
		self.__class__ = VERSIONS[value]
	
	def __init__(self, infile, mode='r', version=None, opf=None):
		super().__init__(infile, mode=mode)
		if version is not None:
			self.version = version
		self.opf = opf
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
		
		if self.mode == 'r':
			self.__init_read()
		elif self.mode == 'w':
			self.__init_write()
		else:
			raise TypeError('mode should be \'r\' or \'w\'')
	
	def __init_read(self):
		if self.opf is not None:
			raise TypeError('Can\'t set the opfpath when opening in \'r\' mode')
		
		with self._open('META-INF/container.xml') as f:
			tree = etree.parse(f)
		self.opf = tree.find('./container:rootfiles/container:rootfile', NS).get('full-path')
		
		with self._open(self.opf) as f:
			opftree = etree.parse(f).getroot()
		
		self.version = self.version or opftree.get('version')
		
		self._read_manifest(opftree)
		self._read_spine(opftree)
		self._read_toc(opftree)
		self._read_meta(opftree)
		
		uid_id = opftree.get('unique-identifier')
		self.uid = next(filter(lambda i: i.get('id') == uid_id, self.meta['identifiers']), None)
	
	def __init_write(self):
		if self.opf is None:
			self.opf = 'content.opf'
		self.uid = AttributedString(uuid.uuid4())
		self.uid['id'] = 'uid_id'
		self.uid['scheme'] = 'uuid'
		self.meta['identifiers'] = [self.uid]
		
		self._writestr('mimetype', b'application/epub+zip', compress_type=zipfile.ZIP_STORED)
		
		container = E['container'].container(
			E['container'].rootfiles(
				E['container'].rootfile({
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
	
	def __exit__(self, *args):
		if self.version is None:
			raise TypeError('Set a version before closing the Epub')
		
		self.meta['dates']['modification'] = datetime.datetime.now()
		
		if self.toc.item is not None:
			self._write_toc()
		pkg = E['opf'].package(
			{'version': self.version, 'unique-identifier': self.uid['id']},
			self._xml_meta(),
			self._xml_manifest(),
			self._xml_spine(),
		)
		self._writestr(self.opf, etree.tostring(pkg, pretty_print=True))
		return super().__exit__(*args)
	
	def _read_toc(self, opf):
		raise NotImplementedError
	
	def _read_meta(self, opf):
		raise NotImplementedError
	
	def _read_manifest(self, opf):
		for item in opf.findall('./opf:manifest/opf:item', NS):
			self.manifest[getxmlattr(item, 'id')] = getxmlattr(item, 'href')
	
	def _read_spine(self, opf):
		for item in opf.findall('./opf:spine/opf:itemref', NS):
			item = self.manifest[getxmlattr(item, 'idref')]
			self.spine.append(item)
	
	def _write_toc(self):
		raise NotImplementedError
	
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
		super().writestr(*args, **kwargs)
	
	def writestr(self, item, data, iid=None, **kwargs):
		if isinstance(item, zipfile.ZipInfo):
			raise NotImplementedError('item should be a path relative to the opfdir or an Item')
		if not isinstance(item, self.manifest.Item) or item.iid not in self.manifest:
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
		href = href.rsplit('#', 1)[0]
		return next(filter(lambda item: item.href == href, self.values()))


class Spine(list):
	def append(self, item):
		if not isinstance(item, Manifest.Item):
			raise TypeError('The spine needs to be a list of Manifest.Item')
		return super().append(item)


class Toc(list):
	def __init__(self, *args, **kwargs):
		self.item = None
		self.title = 'Table of contents'
	
	class Item:
		def __init__(self, href, title):
			self.href = href
			self.title = title
			self.children = Toc()
		
		def __repr__(self):
			return '<Toc.Item {}>'.format(self.__dict__)
	
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
	def __new__(cls, value, data=None):
		return super().__new__(cls, value)
	
	def __init__(self, value, data=None):
		self.data = data or {}
	
	def __repr__(self):
		return '<AttributedString {!r} {}>'.format(str(self), self.data)


class Epub20(Epub):
	_version = '2.0'
	
	def _read_toc(self, opf):
		toc_id = getxmlattr(opf.find('./opf:spine', NS), 'toc')
		if toc_id is None:
			return
		
		def parse(tag):
			for np in tag.findall('./ncx:navMap/ncx:navPoint', NS):
				yield (
					getxmlattr(np.find('./ncx:content', NS), 'src'),
					np.find('./ncx:navLabel/ncx:text', NS).text,
					parse(np),
				)
		
		self.toc.item = self.manifest.pop(toc_id)
		with self.open(self.toc.item) as f:
			ncx = etree.parse(f).getroot()
		
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
	def _read_meta(self, opf):
		metadata = opf.find('./opf:metadata', NS)
		def extract(tag, attrs):
			for t in metadata.findall('dc:' + tag, NS):
				yield AttributedString(t.text, {
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
		if self.toc.item is not None:
			spine.attrib['toc'] = self.toc.item.iid
	
	def _write_toc(self):
		if not re.search(r'^.+\.ncx', self.toc.item.href):
			self.toc.item.href = '{}.{}'.format(self.toc.item.href.rsplit('.', 1)[0], 'ncx')
		
		def navmap(toc):
			for item in toc:
				yield E['ncx'].navPoint(
					E['ncx'].navLabel(E['ncx'].text(item.title)),
					E['ncx'].navMap(*(navmap(item.children))),
				)
		
		toc = E['ncx'].ncx(
			{'version': '2005-1'},
			E['ncx'].head(),
			E['ncx'].docTitle(E['ncx'].text(self.toc.title)),
			E['ncx'].navMap(*navmap(self.toc)),
		)
		
		self._writestr('toc.ncx', etree.tostring(toc, pretty_print=True))


class Epub30(Epub):
	_version = '3.0'
	
	def _read_toc(self, opf):
		toc_item = opf.find('./opf:metadata/opf:item[@properties="nav"]')
		if toc_item is None:
			return
		
		def parse(tag):
			for li in tag.findall('./html:ol/html:li/html:a', NS):
				a = li.find('./html:a', NS)
				yield (getxmlattr(a, 'href'), a.text, parse(np))
		
		self.toc.item = self.manifest.pop(toc_id)
		with self.open(self.toc.item) as f:
			toc = etree.parse(f).getroot()
		
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
	def _read_meta(self, opf):
		metadata = opf.find('./opf:metadata', NS)
		
		def extract(tag, attrs):
			for t in metadata.findall('dc:' + tag, NS):
				res = AttributedString(t.text, {
					k.split(':', 1)[-1]: getxmlattr(t, k)
					for k in attrs
					if getxmlattr(t, k) is not None
				})
				if getxmlattr(tag, 'id') is not None:
					res['id'] = getxmlattr(tag, 'id')
					for refine in metadata.findall('meta/[@refine="#{}"]'.format(res['id'])):
						res[getxmlattr(refine, 'property')] = refine.text
		
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
		
		self._writestr('toc.html', etree.tostring(toc, pretty_print=True, method='html'))


VERSIONS = {e._version: e for e in (Epub20, Epub30)}

NS = {
	'container': 'urn:oasis:names:tc:opendocument:xmlns:container',
	'opf': 'http://www.idpf.org/2007/opf',
	'ops': 'http://www.idpf.org/2007/ops',
	'dc': 'http://purl.org/dc/elements/1.1/',
	'ncx': 'http://www.daisy.org/z3986/2005/ncx/',
	'html': 'http://www.w3.org/1999/xhtml',
}

RNS = {v: k for k, v in NS.items()}

E = {k: builder.ElementMaker(namespace=v, nsmap=NS) for k, v in NS.items()}

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

def ns(name):
	if ':' in name:
		ns, name = name.split(':', 1)
		return '{{{}}}{}'.format(NS[ns], name)
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
