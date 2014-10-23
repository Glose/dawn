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


class Epub(zipfile.ZipFile):
	def __init__(self, infile, mode='r', **kwargs):
		super().__init__(infile, mode=mode)
		if mode == 'r':
			self.__init_read(**kwargs)
		elif mode == 'w':
			self.__init_write(**kwargs)
		else:
			raise TypeError('mode should be \'r\' or \'w\'')
	
	def __init_read(self, version=None):
		with super().open('META-INF/container.xml') as f:
			tree = ET.parse(f)
		self.opf = tree.find('./container:rootfiles/container:rootfile', NS).get('full-path')
		
		with super().open(self.opf) as f:
			opftree = ET.parse(f).getroot()
		self.version = version or opftree.get('version')
		
		self.__spec = SPECS[self.version](self, opftree)
		self.manifest = Manifest()
		self.spine = Spine()
		self.toc = Toc()
		self.meta = {}
		
		for iid, href in self.__spec.read_manifest():
			self.manifest[iid] = href
		for iid in self.__spec.read_spine():
			self.spine.add(self.manifest[iid])
		for title, href, children in self.__spec.read_toc():
			self.toc.append(href, title, children)
		self.meta.update(dict(self.__spec.read_meta()))
		uid_id = opftree.get('unique-identifier')
		self.uid = next(filter(lambda i: i.id == uid_id, self.meta['identifiers']), None)
	
	def __init_write(self, version=None, opf=None):
		if version is None:
			raise TypeError('Version is required when opening an ePub in \'w\' mode')
		self.opf = opf or 'content.opf'
		self.version = version
		self.uid = uuid.uuid4()
		self.__spec = SPECS[self.version](self, opftree)
		self.manifest = Manifest()
		self.spine = Spine()
		self.toc = Toc()
		self.meta = {}
	
	def __exit__(self, *args):
		super().writestr('mimetype', b'application/epub+zip', compress_type=zipfile.ZIP_STORED)
		
		container = ET.Element('container', attrib={
			'version': '1.0',
			'xmlns': self.opfns,
		})
		ET.SubElement(ET.SubElement(root, 'rootfiles'), 'rootfile', attrib={
			'full-path': self.opf,
			'media-type': 'application/oebps-package+xml',
		})
		super().writestr('META-INF/container.xml', ET.tostring(container), compress_type=zipfile.ZIP_STORED)
		
		self.__spec.write_exit()
		return super().__exit__(*args)
	
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


class Spec:
	class AttributeString(str):
		pass
	
	def __init__(self, epub, opf):
		self.opf = opf
		self.epub = epub
	
	def read_manifest(self):
		# yields (id, href)
		raise NotImplementedError
	
	def read_spine(self):
		# yields id
		raise NotImplementedError
	
	def read_toc(self):
		# yields title, href, children
		raise NotImplementedError
	
	def read_meta(self):
		# yields key, val
		raise NotImplementedError
	
	def write_exit(self):
		raise NotImplementedError


class Spec20(Spec):
	def read_manifest(self):
		for item in self.opf.findall('./opf:manifest/', NS):
			yield item.get('id'), item.get('href')
	
	def read_spine(self):
		for item in self.opf.findall('./opf:spine/', NS):
			yield item.get('idref')
	
	def read_toc(self):
		toc_id = self.opf.find('./opf:spine', NS).get('toc')
		if not toc_id:
			return []
		
		def find_childs(tag):
			for np in tag.findall('./ncx:navMap/ncx:navPoint', NS):
				yield (
					np.find('./ncx:navLabel/ncx:text', NS).text,
					np.find('./ncx:content', NS).get('src'),
					find_childs(np),
				)
		
		with self.epub.open(self.epub.manifest[toc_id]) as f:
			ncx = ET.parse(f).getroot()
		yield from find_childs(ncx)
	
	def read_meta(self):
		metadata = self.opf.find('./opf:metadata', NS)
		def extract(tags, attrs=(), only_one=False):
			res = []
			for item in metadata.findall(tags, NS):
				res.append(self.AttributeString(item.text))
				for k in attrs:
					setattr(res[-1], k.split(':', 1)[-1].replace('-', '_'), getxmlattr(item, k))
				if only_one:
					return res[0]
			return None if only_one else res
		yield 'titles', extract('dc:title', ('lang',))
		yield 'creators', extract('dc:creator', ('opf:role', 'opf:file-as'))
		yield 'subjects', extract('dc:subject')
		yield 'description', extract('dc:description', only_one=True)
		yield 'publisher', extract('dc:publisher', only_one=True)
		yield 'contributors', extract('dc:contributor', ('opf:role', 'opf:file-as'))
		yield 'dates', extract('dc:date', ('opf:event',))
		# Drop type
		# Drop format
		yield 'identifiers', extract('dc:identifier', ('id', 'opf:scheme'))
		yield 'source', extract('dc:source', only_one=True)
		yield 'languages', extract('dc:language')
		# Drop relation
		# Drop coverage
		# Drop rights

class Spec30(Spec):
	pass

SPECS = {
	'2.0': Spec20,
	'3.0': Spec30,
}