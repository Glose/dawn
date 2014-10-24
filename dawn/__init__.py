import collections
import datetime
import io
import mimetypes
import posixpath
import oset
import uuid
import xml.etree.ElementTree as ET
import zipfile


NS = {
	'container': 'urn:oasis:names:tc:opendocument:xmlns:container',
	'opf': 'http://www.idpf.org/2007/opf',
	'dc': 'http://purl.org/dc/elements/1.1/',
	'ncx': 'http://www.daisy.org/z3986/2005/ncx/',
}

def getxmlattr(tag, attr, fallback=None):
	if ':' in attr:
		ns, attr = attr.split(':', 1)
		attr = '{{{}}}{}'.format(NS[ns], attr)
	return tag.get(attr, fallback)

def tostring(et, ns):
	res = io.BytesIO()
	ET.ElementTree(et).write(res)#, default_namespace=NS[ns])
	res.seek(0)
	return res.read()

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
		
		with super().open('META-INF/container.xml') as f:
			tree = ET.parse(f)
		self.opf = tree.find('./container:rootfiles/container:rootfile', NS).get('full-path')
		
		if self.version is None:
			with super().open(self.opf) as f:
				opftree = ET.parse(f).getroot()
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
		
		super().writestr('mimetype', b'application/epub+zip', compress_type=zipfile.ZIP_STORED)
		
		container = ET.Element('container:container', version='1.0')
		ET.SubElement(ET.SubElement(container, 'container:rootfiles'), 'container:rootfile', attrib={
			'full-path': self.opf,
			'media-type': 'application/oebps-package+xml',
		})
		super().writestr('META-INF/container.xml', tostring(container, 'container'), compress_type=zipfile.ZIP_STORED)
	
	def _read(self, opf):
		raise NotImplementedError
	
	def _write(self):
		raise NotImplementedError
	
	def write(self, *args, **kwargs):
		raise NotImplementedError('Use writestr')
	
	def writestr(self, item, data, iid=None, compress_type=zipfile.ZIP_DEFLATED):
		if isinstance(item, zipfile.ZipInfo):
			raise NotImplementedError('item should be a path relative to the opfdir or an Item')
		if not isinstance(item, self.manifest.Item):
			item = self.manifest.add(item)
		super().writestr(self.__opfpath(item.href), data, compress_type=compress_type)
		return item
	
	def open(self, item, mode='r', pwd=None):
		if isinstance(item, self.manifest.Item):
			item = item.href
		return super().open(self.__opfpath(item), pwd=pwd)
	
	def __opfpath(self, path):
		return posixpath.join(posixpath.dirname(self.opf), path)


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
		self['item-{}'.format(len(self))] = item
		return item
	
	def __setitem__(self, k, v):
		if isinstance(v, str):
			v = self.Item(k, v)
		if not isinstance(v, self.Item):
			raise TypeError('The manifest needs to be a dict of Manifest.Item')
		super().__setitem__(k, v)
		return v
	
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
			self.manifest[item.get('id')] = item.get('href')
	
	def _read_spine(self, opf):
		for item in opf.findall('./opf:spine/', NS):
			item = self.manifest[item.get('idref')]
			self.spine.add(item)
	
	def _read_toc(self, opf):
		toc_id = opf.find('./opf:spine', NS).get('toc')
		if not toc_id:
			return
		
		def parse(tag):
			for np in tag.findall('./ncx:navMap/ncx:navPoint', NS):
				self.toc.append(
					np.find('./ncx:content', NS).get('src'),
					np.find('./ncx:navLabel/ncx:text', NS).text,
					parse(np),
				)
		
		with self.open(self.manifest[toc_id]) as f:
			ncx = ET.parse(f).getroot()
		
		parse(ncx)
		title_tag = ncx.find('./ncx:docTitle/ncx:text', NS)
		if title_tag is not None:
			self.title = title_tag.text
	
	__meta = [
		# tag, attributes, multiple
		('dc:title', ('lang',), True),
		('dc:creator', ('opf:role', 'opf:file-as'), True),
		('dc:subject', (), True),
		('dc:description', (), False),
		('dc:publisher', (), False),
		('dc:contributor', ('opf:role', 'opf:file-as'), True),
		('dc:date', ('opf:event',), True),
		# Drop type
		# Drop format
		('dc:identifier', ('id', 'opf:scheme'), True),
		('dc:source', (), False),
		('dc:language', (), True),
		# Drop relation
		# Drop coverage
		# Drop rights
	]
	
	def _read_meta(self, opf):
		metadata = opf.find('./opf:metadata', NS)
		def extract(tag, attrs):
			for item in metadata.findall(tag, NS):
				res = AttributedString(item.text)
				for k in attrs:
					res[k.split(':', 1)[-1]] = getxmlattr(item, k)
				yield res
		for tag, attrs, multi in self.__meta:
			key = tag.split(':', 1)[-1]
			if multi:
				key += 's'
			f = list if multi else lambda it: next(it, None)
			self.meta[key] = f(extract(tag, attrs))
	
	def _write_opf(self):
		opf = ET.Element('package', attrib={
			'version': self.version,
			'unique-identifier': self.uid['id'],
		})
		meta = ET.SubElement(opf, 'metadata')
		ET.SubElement(meta, 'dc:format').text = 'application/epub+zip'
		ET.SubElement(meta, 'dc:date', attrib={
			'opf:event': 'publication',
		}).text = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
		
		for tag, attrs, multi in self.__meta:
			key = tag.split(':', 1)[-1]
			if multi:
				key += 's'
			todo = self.meta.get(key)
			if not todo:
				continue
			if not multi:
				todo = [todo]
			for astr in todo:
				ET.SubElement(meta, tag, attrib={
					k: astr[k.split(':', 1)[-1]]
					for k in attrs
				}).text = str(astr)
		
		manifest = ET.SubElement(opf, 'manifest')
		for item in self.manifest.values():
			ET.SubElement(manifest, 'item', attrib={
				'id': item.iid,
				'href': item.href,
				'media-type': item.mimetype,
			})
		
		spine = ET.SubElement(opf, 'spine')
		for item in self.spine:
			ET.SubElement(spine, 'itemref', idref=item.iid)
		
		super().writestr(self.opf, tostring(opf, 'opf'))
	
	def _write_toc(self):
		toc = ET.Element('ncx', version='2055-1')
		ET.SubElement(toc, 'head')
		ET.SubElement(
			ET.SubElement(toc, 'docTitle'),
			'text',
		).text = self.toc.title
		
		def navmap(toc, parent):
			nm = ET.SubElement(parent, 'navMap')
			for item in toc:
				np = ET.SubElement(nm, 'navPoint')
				ET.SubElement(
					ET.SubElement(np, 'navLabel'),
					'text',
				).text = item.title
				ET.SubElement(np, 'content', src=item.href)
				if item.children:
					navmap(item.children, np)
		
		navmap(self.toc, toc)
		self.writestr('toc.ncx', tostring(toc, 'ncx'))
	
	def _read(self, opf):
		self._read_manifest(opf)
		self._read_spine(opf)
		self._read_toc(opf)
		self._read_meta(opf)
	
	def __exit__(self, *args):
		self._write_opf()
		self._write_toc()
		super().__exit__(*args)

class Epub30(Epub):
	_version = '3.0'
	
	def __exit__(self, *args):
		raise NotImplementedError


VERSIONS = {e._version: e for e in (Epub20, Epub30)}
