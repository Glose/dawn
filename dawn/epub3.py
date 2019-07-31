import lxml.etree

from .epub import AttributedString
from .epub import Epub
from .utils import E
from .utils import getxmlattr
from .utils import ns
from .utils import NS
from .utils import parse_date


class Epub30(Epub):
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
		if self.toc.item is None:
			self.toc.item = self.manifest.Item('__toc', 'toc.html')

		def ol(toc):
			for item in toc:
				yield E['html'].ol(
					E['html'].a(item.title, {'href': item.href}),
					E['html'].ol(*(ol(item.children))),
				)

		toc = E['html'].html(
			{'version': '2005-1'},
			E['html'].head(),
			E['html'].h1(self.toc.title or ''),
			E['html'].ol(*ol(self.toc)),
		)

		data = lxml.etree.tostring(toc, pretty_print=True, method='html')
		self.writestr(self.toc.item, data)
