## dawn

```python
import dawn

with dawn.Epub('output.epub', mode='w', version='2.0') as epub:
	epub.meta['creators'] = [dawn.AS('Me', role='author')]
	epub.meta['description'] = dawn.AS('Awesome book')
	epub.meta['title'] = dawn.AS('My ePub', lang='en')
	
	for href, title in [
		('README.md', 'README'),
		('dawn.py', 'dawn/__init__.py'),
	]:
		with open(href, 'r') as f:
			item = epub.writestr(href, f.read())
		epub.spine.append(item)
		epub.toc.append(href, title=title)
```