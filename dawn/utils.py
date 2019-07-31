import datetime
import lxml.etree
import lxml.builder


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
