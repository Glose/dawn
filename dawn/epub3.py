import lxml.etree
import uuid

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
		toc_id = opftree.find('./opf:manifest/opf:item[@properties="nav"]', NS)
		if toc_id is None:
			return
		toc_id = getxmlattr(toc_id, 'id')

		def parse(tag):
			if tag is None:
				return
			for li in tag.findall('./html:li', NS):
				a = li.find('./html:a', NS)
				nested = li.find('./html:ol', NS)
				href = getxmlattr(a, 'href')
				if href is not None:
					yield (href, a.text, parse(nested))

		self.toc.item = self.manifest.pop(toc_id)
		with self.open(self.toc.item) as f:
			toc = lxml.etree.parse(f).getroot()

		nav = toc.find('.//html:nav[@ops:type="toc"]', NS)

		for a in parse(nav.find('./html:ol', NS)):
			self.toc.append(*a)

		title_tag = nav.find('.//html:h2', NS)
		if title_tag is not None:
			self.toc.title = title_tag.text

	__meta = [
		# tag, attributes, multiple
		('identifier', ('identifier-type',), True), # identifier-type is mapped to scheme
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
					for refine in metadata.findall('opf:meta/[@refines="#{}"]'.format(res['id']), NS):
						res[getxmlattr(refine, 'property')] = refine.text
				yield res

		for tag, attrs, multi in self.__meta:
			f = list if multi else lambda it: next(it, None)
			self.meta[tag + ('s' if multi else '')] = f(extract(tag, attrs))

		for identifier in self.meta['identifiers']:
			if 'identifier-type' in identifier:
				identifier['scheme'] = identifier.pop('identifier-type')

		for tag, k in self.__dates:
			date = metadata.find('opf:meta/[@property="dcterms:{}"]'.format(tag), NS)
			if date is not None:
				self.meta['dates'][k] = parse_date(date.text)

	def _xml_meta(self):
		meta = super()._xml_meta()

		for tag, k in self.__dates:
			val = self.meta['dates'].get(k)
			if val:
				meta.append(E['opf'].meta(
					{'property': 'dcterms:{}'.format(tag)},
					val.strftime('%Y-%m-%dT%H:%M:%SZ'),
				))

		for tag, attrs, multi in self.__meta:
			todo = self.meta.get(tag + ('s' if multi else ''))
			if not todo:
				continue
			if not multi:
				todo = [todo]
			for astr in todo:
				attrs_to_add = dict(astr)
				m = getattr(E['dc'], tag)(str(astr))
				for k in attrs:
					if k == 'scheme': k = 'identifier-type'
					val = attrs_to_add.pop(k.split(':', 1)[-1], None)
					if val:
						m.attrib[ns(k)] = val
				meta.append(m)
				if attrs_to_add:
					m.attrib['id'] = str(uuid.uuid4())
					for k in attrs_to_add:
						meta.append(E['opf'].meta(str(astr[k]), {
							'refines': '#{}'.format(m.attrib['id']),
							'property': k,
						}))

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
		def ol(toc):
			res = E['html'].ol()
			for item in toc:
				np = E['html'].li(
					E['html'].a(item.title, {'href': item.href}),
				)
				if item.children:
					np.append(ol(item.children))
				res.append(np)
			return res

		data = E['html'].html(
			E['html'].head(
				E['html'].meta({ns('html:charset'): 'utf-8'}),
			),
			E['html'].body(
				E['html'].nav(
					{ns('ops:type'): 'toc'},
					E['html'].h2(self.toc.title or ''),
					ol(self.toc),
				),
			),
		)
		data = lxml.etree.tostring(data, pretty_print=True, method='html')

		if self.toc.item is None:
			self.toc.item = self.manifest.add('toc.html')
		self.writestr(self.toc.item, data)
		del self.manifest[self.toc.item.iid]
