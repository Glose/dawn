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

def _ser_toc_item(it):
	res = {'href': it.href, 'title': it.title}
	assert it.children.title is None
	if it.children:
		res['children'] = [_ser_toc_item(c) for c in it.children]
	return res

def _json_default(o):
	if isinstance(o, datetime.datetime):
		return o.isoformat()

@pytest.mark.parametrize('expected', samples)
def test_read(expected):
	epub = expected.replace('.expected.json', '.epub')
	dbg = expected.replace('.expected.json', '.debug.json')

	with dawn.open(epub) as epub:
		res = {
			'uid': epub.uid,
			'version': epub.version,
			'spine': [v.iid for v in epub.spine],
			'manifest': {k: [v.iid, v.href] for k, v in epub.manifest.items()},
			'toc': [epub.toc.title, [_ser_toc_item(it) for it in epub.toc]],
			'meta': epub.meta,
		}

	# stringify the dates
	res = json.dumps(res, default=_json_default)
	res = json.loads(res)

	with open(dbg, 'w') as f:
		json.dump(res, f, indent=4)

	with open(expected, 'r') as f:
		exp = json.load(f)
	assert res == exp

	os.unlink(dbg)


def test_wrong_mode():
	with pytest.raises(TypeError):
		dawn.open(None, 'a')
