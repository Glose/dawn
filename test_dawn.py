import datetime
import dawn
import glob
import json
import lxml.html
import os
import pytest
import urllib.request


samples = glob.glob('samples/data/*.expected.json')
print(samples)

_dummy = 'samples/data/9780312591199 - Dummy ePub - Glose.epub'
@pytest.fixture
def dummy():
	if not os.path.exists(_dummy):
		pytest.skip('Missing dummy fixture')
	with dawn.open(_dummy) as e:
		yield e

@pytest.mark.parametrize('expected', samples)
def test_read(expected):
	epub = expected.replace('.expected.json', '.epub')
	dbg = expected.replace('.expected.json', '.debug.json')

	if not os.path.exists(epub):
		pytest.skip('Missing fixture')

	def _ser_toc_item(it):
		res = {'href': it.href, 'title': it.title}
		assert it.children.title is None
		if it.children:
			res['children'] = [_ser_toc_item(c) for c in it.children]
		return res

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
