"""Parse the Markdown pages and read metadata from the library without importing bpy."""
import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTENT = ROOT / 'docs/site'
TOYS = CONTENT / 'toys'
SECTIONS = [('start', 'Start'), ('reference', 'Reference'), ('guides', 'Guides'), ('', 'For LLMs')]


# ---------------------------------------------------------------- pages
class Page:
    def __init__(self, path):
        self.path = path
        text = path.read_text(encoding='utf-8')
        meta, body = {}, text
        if text.startswith('---\n'):
            head, _, body = text[4:].partition('\n---\n')
            key = None
            for line in head.split('\n'):
                if line.startswith('  ') and key:
                    meta[key] += ' ' + line.strip()
                elif ':' in line:
                    key, _, v = line.partition(':')
                    key = key.strip()
                    meta[key] = v.strip()
        self.meta, self.body = meta, body
        rel = path.relative_to(CONTENT)
        self.section = rel.parts[0] if len(rel.parts) > 1 else ''
        self.here = rel.with_suffix('.html').as_posix()
        self.title = meta.get('title', path.stem)
        self.nav = meta.get('nav', self.title)
        self.order = float(meta.get('order', 99))


def pages():
    articles = (Page(p) for p in CONTENT.rglob('*.md') if p.name not in {'README.md', 'index.md'})
    return [Page(CONTENT / 'index.md'), *sorted(articles, key=lambda p: (p.section, p.order, p.title))]


# ---------------------------------------------------------------- blocks
def directives(body):
    """Yield ('md', text) and ('dir', kind, args, fields) in order. A directive is ::: kind args ... :::"""
    out, buf, lines, i = [], [], body.split('\n'), 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r'^:::\s*(\w+)\s*(.*)$', line)
        if m:
            if buf:
                out.append(('md', '\n'.join(buf)))
                buf = []
            kind, args, fields = m.group(1), m.group(2).split(), []
            i += 1
            while i < len(lines) and lines[i].strip() != ':::':
                l = lines[i]
                if l.strip().startswith('```'):  # a code example inside the directive
                    code, i = [], i + 1
                    while i < len(lines) and not lines[i].strip().startswith('```'):
                        code.append(lines[i])
                        i += 1
                    fields.append(('code', '\n'.join(code)))
                elif l.startswith('  ') and fields:
                    k, v = fields[-1]
                    fields[-1] = (k, v + ' ' + l.strip())
                elif l.strip():
                    k, _, v = l.partition(':')
                    if k.startswith('param '):  # param name: text, the name may hold colons only inside backticks
                        k, _, v = l.partition(': ')
                    fields.append((k.strip(), v.strip()))
                i += 1
            out.append(('dir', kind, args, fields))
        else:
            buf.append(line)
        i += 1
    if buf:
        out.append(('md', '\n'.join(buf)))
    return out


def fiche_names(page):
    """(name, anchor) for every name a page's fiches document; the first name is the fiche's anchor."""
    out = []
    for block in directives(page.body):
        if block[0] == 'dir' and block[1] == 'fiche':
            out.extend((name, anchor(name)) for name in block[2])
    return out


def anchor(name):
    return re.sub(r'[^A-Za-z0-9_-]+', '-', name).strip('-')


def slug(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


# ---------------------------------------------------------------- public names
def library_metadata():
    """Read __version__ and __all__ as literals so the build does not require Blender."""
    source = ROOT / 'src/sand3d/__init__.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    values = {target.id: ast.literal_eval(node.value)
              for node in tree.body if isinstance(node, ast.Assign)
              for target in node.targets if isinstance(target, ast.Name)
              and target.id in {'__version__', '__all__'}}
    methods = ['Frame.offset', 'Frame.turn', 'Frame.move', 'Frame.point', 'Frames.jitter', 'ob.face', 'ob.edge']
    return values['__version__'], values['__all__'] + methods
