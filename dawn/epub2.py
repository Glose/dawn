import itertools
import lxml.etree

from .epub import AttributedString
from .epub import Epub
from .utils import E
from .utils import getxmlattr
from .utils import ns
from .utils import NS
from .utils import parse_date


class Epub20(Epub):
	version = '2.0'

	def _read_toc(self, opftree):
		toc_id = getxmlattr(opftree.find('./opf:spine', NS), 'toc')
		if toc_id is None:
			return

		def parse(tag):
			for np in tag.findall('./ncx:navPoint', NS):
				yield (
					getxmlattr(np.find('./ncx:content', NS), 'src'),
					np.find('./ncx:navLabel/ncx:text', NS).text,
					parse(np),
				)

		self.toc.item = self.manifest.pop(toc_id)
		with self.open(self.toc.item) as f:
			ncx = lxml.etree.parse(f).getroot()

		for a in parse(ncx.find('./ncx:navMap', NS)):
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
				yield AttributedString(t.text or '', **{
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
				tag = getattr(E['dc'], tag)(str(astr))
				for k in attrs:
					val = astr.get(k.split(':', 1)[-1])
					if val:
						tag.attrib[ns(k)] = val
				meta.append(tag)

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
		return spine

	def _write_toc(self):
		if self.toc.item is None:
			self.toc.item = self.manifest.Item('__toc', 'toc.ncx')

		ids = itertools.count()

		def navpoints(toc):
			for item in toc:
				np = E['ncx'].navPoint(
					{'id': 'np-{}'.format(next(ids))},
					E['ncx'].navLabel(E['ncx'].text(item.title)),
					E['ncx'].content({'src': item.href}),
				)
				if item.children:
					for c in navpoints(item.children):
						np.append(c)
				yield np

		toc = E['ncx'].ncx(
			{'version': '2005-1'},
			E['ncx'].head(),
			E['ncx'].docTitle(E['ncx'].text(self.toc.title or '')),
			E['ncx'].navMap(*navpoints(self.toc)),
		)

		data = lxml.etree.tostring(toc, pretty_print=True)
		self.writestr(self.toc.item, data)
