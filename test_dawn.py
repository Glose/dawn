import datetime
import dawn
import glob
import json
import lxml.html
import os
import pytest
import urllib.request


samples = glob.glob('samples/*.expected.json')

if not all(os.path.exists(s.replace('.expected.json', '.epub')) for s in samples):
	with urllib.request.urlopen('http://idpf.github.io/epub3-samples/30/samples.html') as f:
		index = f.read()
	soup = lxml.html.fromstring(index)
	for a in soup.xpath('//a[contains(@href, ".epub")]'):
		href = a.get('href')
		_, fn = href.rsplit('/', 1)
		with \
			urllib.request.urlopen(href) as s, \
			open('samples/{}'.format(fn), 'wb') as d:
			d.write(s.read())

	for p in glob.glob('../Glose ePubs/*/*.epub'):
		fn = os.path.basename(p).replace('.epub', '.expected.json')
		if fn not in samples:
			continue
		with open(p, 'rb') as r, open('samples/{}'.format(fn), 'wb') as w:
			w.write(r.read())


_dummy = 'samples/9780312591199 - Dummy ePub - Glose.epub'
@pytest.fixture
def dummy():
	if not os.path.exists(_dummy):
		pytest.skip('Missing dummy fixture')
	with dawn.open(_dummy) as e:
		yield e

def _ser_toc_item(it):
	res = {'href': it.href, 'title': it.title}
	assert it.children.title is None
	if it.children:
		res['children'] = [_ser_toc_item(c) for c in it.children]
	return res

def _json_default(o):
	if isinstance(o, datetime.datetime):
		return o.isoformat()
	if isinstance(o, dawn.AttributedString):
		return repr(o)

@pytest.mark.parametrize('expected', samples)
def test_read(expected):
	epub = expected.replace('.expected.json', '.epub')
	dbg = expected.replace('.expected.json', '.debug.json')

	if not os.path.exists(epub):
		pytest.skip('Missing fixture')

	with dawn.open(epub) as epub:
		res = {
			'uid': epub.uid,
			'version': epub.version,
			'spine': [v.iid for v in epub.spine],
			'manifest': {k: [v.iid, v.href, v.mimetype] for k, v in epub.manifest.items()},
			'toc': [epub.toc.title, [_ser_toc_item(it) for it in epub.toc]],
			'meta': {k: repr(v) for k, v in epub.meta.items()},
		}

	with open(dbg, 'w') as f:
		json.dump(res, f, indent=4)

	with open(expected, 'r') as f:
		exp = json.load(f)
	assert res == exp

	os.unlink(dbg)

def test_wrong_mode():
	with pytest.raises(TypeError):
		dawn.open(None, 'a')

def test_repr(dummy):
	assert repr(dummy) == '<Epub 2.0 (len(manifest): 1, len(spine): 1)>'
	assert repr(dummy.manifest) == "{'id0': <Manifest.Item {'iid': 'id0', 'href': 'data.html'}>}"
	assert repr(dummy.spine) == "[<Manifest.Item {'iid': 'id0', 'href': 'data.html'}>]"
	assert repr(dummy.toc) == "[<Toc.Item {'href': 'data.html', 'title': 'Dummy chapter', 'children': []}>]"
	assert repr(dummy.meta['titles'][0]) == "<AttributedString '9780312591199 - Dummy ePub' {}>"

def test_manifest_byhref(dummy):
	it = dummy.manifest.byhref('data.html#test#blih')
	with pytest.raises(KeyError):
		dummy.manifest.byhref('wrong')
