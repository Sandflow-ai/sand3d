"""Check links, assets and fragment targets in the published site."""
import re
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

from content import ROOT

SITE = ROOT / 'site'


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.anchors = set()
        self.links = set()
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if not value:
                continue
            if key == 'id' or (tag == 'a' and key == 'name'):
                self.anchors.add(value)
            if key in {'href', 'src', 'data-glb', 'poster'}:
                self.links.add(value)


def resolve(source, url, domain):
    target = urlsplit(url)
    if target.scheme not in {'', 'http', 'https'} or (target.netloc and target.netloc != domain):
        return None
    path = unquote(target.path)
    if target.netloc or path.startswith('/'):
        return (SITE / path.lstrip('/')).resolve(), unquote(target.fragment)
    destination = (source.parent / path).resolve() if path else source
    return destination, unquote(target.fragment)


def main():
    domain = (SITE / 'CNAME').read_text(encoding='utf-8').strip()
    pages = {path: Document(path.read_text(encoding='utf-8')) for path in SITE.rglob('*.html')}
    sources = {path: doc.links for path, doc in pages.items()}
    for path in SITE.rglob('*.css'):
        sources[path] = set(re.findall(r'''url\(\s*["']?([^"'\s)]+)["']?\s*\)''',
                                       path.read_text(encoding='utf-8')))
    errors = []
    checked = 0
    for path, urls in sorted(sources.items()):
        for url in sorted(urls):
            target = resolve(path, url, domain)
            if target is None:
                continue
            dest, fragment = target
            if dest.is_dir():
                dest /= 'index.html'
            checked += 1
            if not dest.is_relative_to(SITE) or not dest.is_file():
                errors.append(f'{path.relative_to(SITE)}: missing file for {url}')
            elif fragment and dest in pages and fragment not in pages[dest].anchors:
                errors.append(f'{path.relative_to(SITE)}: missing fragment for {url}')
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'{checked} local links checked across {len(pages)} HTML pages')


if __name__ == '__main__':
    main()
