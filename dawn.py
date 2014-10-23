import mimetypes
import oset
import zipfile
import xml.etree.ElementTree as ET


class Epub(zipfile.ZipFile):
	specs = {}
	
	def __init__(self, infile, mode='r', opfdir=None, version=None):
		super().__init__(infile, mode=mode)
		if mode == 'r':
			if opfdir is not None:
				raise TypeError('Can\'t set a custom opfdir when opening an epub in read mode')
			container = ET.fromstring(super().read('META-INF/container.xml')).getroot()
			rootfile = container.find('./root-files/root-file[0]').attrib['full-path']
			self.opfdir = rootfile.rsplit('/', 1)[0]
			
			pkg = ET.fromstring(super().read(rootfile)).getroot()
			self.version = version or pkg.attrib['version']
		elif mode == 'w':
			if version is None:
				raise TypeError('Version is required when opening an ePub in \'w\' mode')
			self.version = version
			self.opfdir = opfdir or ''
		else:
			raise TypeError('mode should be \'r\' or \'w\'')
		
		self.spec = self.specs[self.version](super())
		self.manifest = Manifest()
		self.spine = Spine()
		self.toc = Toc()
		self.meta = {}
		
		if mode == 'w':
			for iid, href in self.spec.read_manifest():
				self.manifest.add(href, iid=iid)
			for iid in self.spec.read_spine():
				self.spine.add(self.manifest.byiid(iid))
			for href, title, children in self.spec.read_toc():
				self.toc.append(href, title, children)
			self.meta.update(self.spec.read_meta())
	
	def __exit__(self, *args):
		super().writestr('mimetype', b'application/epub+zip', compress_type=zipfile.ZIP_STORED)
		
		container = ET.Element('container', attrib={
			'version': '1.0',
			'xmlns': 'urn:oasis:names:tc:opendocument:xmlns:container',
		})
		ET.SubElement(ET.SubElement(root, 'rootfiles'), 'rootfile', attrib={
			'full-path': self.opfpath('content.opf'),
			'media-type': 'application/oebps-package+xml',
		})
		super().writestr('META-INF/container.xml', ET.dump(container), compress_type=zipfile.ZIP_STORED)
		
		self.spec.write_exit()
		return super().__exit__(*args)
	
	def write(self, *args, **kwargs):
		raise NotImplementedError('Use writestr')
	
	def writestr(self, item, data, iid=None, compress_type=zipfile.ZIP_DEFLATED):
		if isinstance(item, zipfile.ZipInfo):
			raise NotImplementedError('item should be a path relative to the opfdir or an Item')
		if not isinstance(item, self.manifest.Item):
			item = self.manifest.add(item)
		super().writestr('/'.join(self.opfdir, item.href), data, compress_type=compress_type)
		return item
	
	def read(self, item, pwd=None):
		if isinstance(item, self.manifest.Item):
			item = item.href
		return super().read(self.opfpath(item), pwd=pwd)
	
	def open(self, item, mode='r', pwd=None):
		if isinstance(item, self.manifest.Item):
			item = item.href
		return super().open(self.opfpath(item), pwd=pwd)
	
	def opfpath(self, path):
		return '/'.join(self.opfdir, path)


class Manifest(set):
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
	
	def add(self, item, iid=None):
		if isinstance(item, str):
			item = self.Item(iid or 'item-{}'.format(len(self)), item)
		if not isinstance(item, self.Item):
			raise TypeError('The manifest needs to be a set of Manifest.Item')
		super().add(item)
		return item
	
	def byhref(self, href):
		href = href.rsplit('#', 1)[0]
		return next(filter(lambda item: item.href == href, self))
	
	def byiid(self, iid):
		return next(filter(lambda item: item.iid == iid, self))


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
	def __init__(self, zipfile):
		self.zipfile = zipfile
	
	def read_manifest(self):
		raise NotImplementedError
	
	def read_spine(self):
		raise NotImplementedError
	
	def read_toc(self):
		raise NotImplementedError
	
	def read_meta(self):
		raise NotImplementedError
	
	def write_exit(self):
		raise NotImplementedError


class Spec20(Spec):
	pass
Epub.specs['2.0'] = Spec20


class Spec30(Spec):
	pass
Epub.specs['3.0'] = Spec30
