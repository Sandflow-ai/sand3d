"""Build the human documentation in site/ with the Python standard library."""
import html
import re
from pathlib import Path

from content import ROOT, SECTIONS, TOYS, anchor, directives, fiche_names, library_metadata, pages, slug

SITE = ROOT / 'site'
VERSION, PUBLIC_NAMES = library_metadata()
esc = html.escape

# ---------------------------------------------------------------- navigation
PAGES = pages()
NAV = [
    (title, [(p.nav, p.here) for p in PAGES if p.section == section])
    for section, title in SECTIONS
]
NAV[0][1].insert(0, ('Overview', 'index.html'))
LEGACY = ('api.html', 'guidelines.html', 'quickstart.html', 'gallery.html', 'tokens.html')


def rel(here, target):
    """Relative link from page `here` to site path `target` (anchors kept)."""
    depth = here.count('/')
    return '../' * depth + target


def link(here, target, text, cls=''):
    return f'<a class="{cls}" href="{rel(here, target)}">{text}</a>'


def topbar(here):
    burger = ('<button class="burger" id="burger" aria-label="Documentation menu" aria-controls="side" aria-expanded="false">'
              '<span></span><span></span><span></span></button>')
    items = [link(here, 'reference/profiles.html', 'Docs', 'on'), link(here, 'gallery.html', 'Gallery'),
             link(here, 'llms.html', 'For LLMs')]
    return f'''<header class="top"><div class="topin">{burger}
<a class="titre" href="{rel(here, 'index.html')}"><img src="{rel(here, 'assets/sandflow-symbol-black.svg')}" alt="">sand3d</a>
<nav class="main" aria-label="Main">{''.join(items)}</nav>
<span class="right"><span class="ver">{VERSION}</span><a class="gh" href="https://github.com/Sandflow-ai/sand3d"><img src="{rel(here, 'assets/github.svg')}" alt="">GitHub</a></span>
</div></header>'''


def sidebar(here, sections):
    out = []
    for group, pages in NAV:
        out.append(f'<p class="grp">{group}</p><ul>')
        for title, target in pages:
            if target == here:
                subs = ''.join(f'<li><a href="#{a}">{esc(t)}</a></li>' for a, t in sections)
                out.append(f'<li class="cur"><a href="{rel(here, target)}" aria-current="page">{title}</a><ul class="subs">{subs}</ul></li>')
            else:
                out.append(f'<li>{link(here, target, title)}</li>')
        out.append('</ul>')
    out.append(f'<ul class="mobile-gallery"><li>{link(here, 'gallery.html', 'Gallery')}</li></ul>')
    return '<aside class="side" id="side"><nav aria-label="Documentation">' + ''.join(out) + '</nav></aside>'


def onpage(sections):
    items = ''.join(f'<li><a href="#{a}">{esc(t)}</a></li>' for a, t in sections)
    return f'<aside class="toc"><p class="grp">On this page</p><ul>{items}</ul></aside>', \
           f'<details class="toc-m"><summary>On this page</summary><ul>{items}</ul></details>'


def document(here, title, body, sections, crumb):
    css = rel(here, 'assets/site.css'), rel(here, 'assets/docs.css')
    toc, toc_m = onpage(sections) if sections else ('', '')
    has_model = ' data-glb="' in body
    body = f'''<div class="shell">{sidebar(here, sections)}<div class="scrim" id="scrim"></div>
<main class="doc"><p class="crumb">{crumb}</p>{toc_m}{body}{footer(here)}</main>{toc}</div>'''
    imports = ('<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js",'
               '"three/addons/":"https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/"}}</script>'
               f'<script type="module" src="{rel(here, "assets/viewer.js")}"></script>') if has_model else ''
    return f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(title)}</title>
<link rel="icon" href="{rel(here, 'assets/sandflow-symbol-black.svg')}">
<link rel="stylesheet" href="{css[0]}"><link rel="stylesheet" href="{css[1]}">
</head><body>{topbar(here)}{body}
<script src="{rel(here, 'assets/docs.js')}"></script>{imports}</body></html>'''


def footer(here):
    return (f'<div class="fin"><span>sand3d {VERSION} · Apache-2.0 · <a href="https://github.com/Sandflow-ai/sand3d">source</a></span>'
            f'<img src="{rel(here, "assets/sandflow-signature.svg")}" alt="Sandflow"></div>')


# ---------------------------------------------------------------- code
KW = set('def return for in if else elif import as from lambda and or not is None True False while with class yield pass break continue try except raise'.split())
TOKEN = re.compile(r'''(?P<s>(?:[rRbBfF]{1,2})?(?:"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'))'''
                   r'''|(?P<c>\#[^\n]*)|(?P<n>(?<![\w.])(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)'''
                   r'''|(?P<vb>(?<=s3d\.)[A-Za-z_]\w*)|(?P<w>[A-Za-z_]\w*)''')


def highlight(code):
    """Highlight Python using the existing site’s token classes."""
    def tok(m):
        kind = m.lastgroup
        text = esc(m.group())
        if kind == 'w':
            return f'<span class="k">{text}</span>' if m.group() in KW else text
        return f'<span class="{kind}">{text}</span>'
    out, last = [], 0
    for m in TOKEN.finditer(code):
        out.append(esc(code[last:m.start()]))
        out.append(tok(m))
        last = m.end()
    out.append(esc(code[last:]))
    return ''.join(out)


def media(name, suffix):
    return f'assets/examples/{name}.{suffix}'


def shown(here, name, alt, cls=''):
    image, model = media(name, 'webp'), media(name, 'glb')
    if not (SITE / image).is_file():
        raise SystemExit(f'{here}: missing image {image}')
    controls = ''
    if (SITE / model).is_file():
        controls = (f'<button type="button" class="activate" data-glb="{rel(here, model)}" '
                    f'aria-label="{esc(alt)}: turn in 3D"><span class="hint">Turn in 3D</span></button>'
                    '<span class="msg" role="status"></span>')
    return (f'<div class="stage {cls}"><img src="{rel(here, image)}" '
            f'alt="{esc(alt)}" loading="lazy">{controls}</div>')


def toy_source(name):
    return (TOYS / f'{name}.py').read_text(encoding='utf-8').strip()


INDEX = {}   # public name -> site path#anchor, from every page's fiches


def target(here, ref):
    """A link target written in content: 'reference/edits#cut', '#local', 'https://…', 'llms'."""
    if re.match(r'^[a-z]+://', ref) or ref.startswith('mailto:'):
        return ref
    if ref.startswith('#'):
        return ref
    path, _, frag = ref.partition('#')
    if not path.endswith(('.html', '.md', '.txt')):
        path += '.html'
    return rel(here, path) + (f'#{frag}' if frag else '')


CODE_NAME = re.compile(r'^(?:s3d\.)?((?:ob|Frame|Frames)\.\w+|[A-Za-z_]\w*)(?:\(.*\))?$')


def inline(here, text, own=()):
    """Inline Markdown: `code` (linked to its fiche when it names one), **bold**, *em*, [text](target)."""
    fragments = []

    def replace_inline(match):
        label, ref, word = match.groups()
        if word is not None:
            fragment = f'<code>{esc(word)}</code>'
            name = CODE_NAME.fullmatch(word)
            if name and name[1] not in own and name[1] in INDEX:
                fragment = f'<a class="vlink" href="{rel(here, INDEX[name[1]])}">{fragment}</a>'
        else:
            label = re.sub(r'`([^`]+)`', r'<code>\1</code>', esc(label))
            fragment = f'<a href="{esc(target(here, ref))}">{label}</a>'
        fragments.append(fragment)
        return f'\x00{len(fragments) - 1}\x00'

    text = re.sub(r'\[([^\]]+)\]\(([^)\s]+)\)|`([^`]+)`', replace_inline, text)
    text = esc(text, quote=False)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])', r'<em>\1</em>', text)
    return re.sub(r'\x00(\d+)\x00', lambda m: fragments[int(m.group(1))], text)


def md_blocks(here, md, sections, own=()):
    """Block Markdown: ## and ### headings ({#id}), paragraphs, - and 1. lists (indented continuation),
    ```python fences, > notes, | tables |."""
    lines, out, i = md.split('\n'), [], 0
    para = []

    def flush():
        if para:
            out.append(f'<p>{inline(here, " ".join(para), own)}</p>')
            para.clear()
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s:
            flush()
            i += 1
            continue
        m = re.match(r'^(#{2,4})\s+(.*?)(?:\s*\{#([\w-]+)\})?\s*$', line)
        if m:
            flush()
            level, title, hid = len(m.group(1)), m.group(2), m.group(3) or slug(m.group(2))
            if level == 2:
                sections.append((hid, re.sub(r'`', '', title)))
            out.append(f'<h{level} id="{hid}">{inline(here, title, own)}</h{level}>')
            i += 1
            continue
        if s.startswith('```'):
            flush()
            lang, code = s[3:].strip(), []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code.append(lines[i])
                i += 1
            i += 1
            body = '\n'.join(code)
            out.append(f'<pre class="code">{highlight(body) if lang in ("", "python", "py") else esc(body)}</pre>')
            continue
        if re.match(r'^(- |\d+\. )', line):
            flush()
            ordered = not line.startswith('- ')
            items = []
            while i < len(lines):
                l = lines[i]
                if re.match(r'^(- |\d+\. )', l) and (l.startswith('- ') != ordered):
                    items.append([re.sub(r'^(- |\d+\. )', '', l)])
                elif items and (l.startswith('  ') or (l.strip() and not re.match(r'^(#|```|>|\||:::)', l))):
                    items[-1].append(l[2:] if l.startswith('  ') else l)
                elif not l.strip() and i + 1 < len(lines) and (lines[i + 1].startswith('  ')):
                    items[-1].append('')
                else:
                    break
                i += 1
            tag = 'ol' if ordered else 'ul'
            inner = ''.join(f'<li>{md_blocks(here, chr(10).join(it), [], own)}</li>' for it in items)
            out.append(f'<{tag} class="md">{inner}</{tag}>')
            continue
        if s.startswith('>'):
            flush()
            note = []
            while i < len(lines) and lines[i].strip().startswith('>'):
                note.append(lines[i].strip()[1:].strip())
                i += 1
            out.append(f'<div class="note">{md_blocks(here, chr(10).join(note), [], own)}</div>')
            continue
        if s.startswith('|'):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                rows.append([c.strip() for c in lines[i].strip().strip('|').split('|')])
                i += 1
            head, rest = rows[0], [r for r in rows[1:] if not all(re.match(r'^:?-+:?$', c) for c in r)]
            th = ''.join(f'<th>{inline(here, c, own)}</th>' for c in head)
            trs = ''.join('<tr>' + ''.join(f'<td>{inline(here, c, own)}</td>' for c in r) + '</tr>' for r in rest)
            out.append(f'<div class="tablewrap"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>')
            continue
        para.append(s)
        i += 1
    flush()
    return ''.join(out)


def fiche(here, names, fields):
    get = lambda k: [v for kk, v in fields if kk == k]
    one = lambda k: (get(k) or [''])[0]
    own = set(names)
    extra = ''.join(f'<span id="{anchor(n)}" class="alias"></span>' for n in names[1:])
    sigs = ''.join(f'<div class="sigline"><code>{esc(s)}</code></div>' for s in get('sig'))
    params = ''.join(f'<dt><code>{esc(k[6:].strip())}</code></dt><dd>{inline(here, v, own)}</dd>'
                     for k, v in fields if k.startswith('param '))
    html_ = [f'<article class="verb" id="{anchor(names[0])}">{extra}<h3>{esc(one("title") or ", ".join(names))}</h3>{sigs}',
             f'<div class="what">{md_blocks(here, one("what"), [], own)}</div>' if one('what') else '',
             f'<dl class="params">{params}</dl>' if params else '']
    for toy in get('toy'):
        name, _, note = toy.partition('|')
        name, note = name.strip(), note.strip() or one('note')
        code = toy_source(name)
        html_.append(f'<h4>Example</h4><div class="pair">{shown(here, name, note or name)}'
                     f'<div class="codecol"><pre class="code">{highlight(code)}</pre>'
                     f'{f"<p class=cap>{inline(here, note, own)}</p>" if note else ""}</div></div>')
    for code in get('code'):
        html_.append(f'<h4>Example</h4><pre class="code">{highlight(code)}</pre>')
    if one('limits'):
        html_.append(f'<div class="limits"><b>Limits.</b> {inline(here, one("limits"), own)}</div>')
    if one('see'):
        html_.append(f'<p class="see">See also: {inline(here, one("see"), own)}</p>')
    return ''.join(html_) + '</article>'


def directive(here, kind, args, fields):
    get = lambda k: [v for kk, v in fields if kk == k]
    one = lambda k: (get(k) or [''])[0]
    if kind == 'fiche':
        return fiche(here, args, fields)
    if kind == 'example':
        name, note = args[0], one('note')
        code = toy_source(name)
        return (f'<div class="pair example">{shown(here, name, note or name)}<div class="codecol"><pre class="code">'
                f'{highlight(code)}</pre>{f"<p class=cap>{inline(here, note)}</p>" if note else ""}</div></div>')
    if kind == 'figure':
        name, note = args[0], one('note')
        cls = 'hero' if 'hero' in args[1:] else ''
        return f'<figure class="fig">{shown(here, name, note or name, cls)}{f"<figcaption>{inline(here, note)}</figcaption>" if note else ""}</figure>'
    if kind == 'scene':
        name, title, note = args[0], one('title') or args[0], one('note')
        code = (ROOT / one('program')).read_text(encoding='utf-8').strip() if one('program') else toy_source(name)
        n = code.count('\n') + 1
        sid = anchor(name)
        return (f'<article class="scene" id="{sid}"><h3>{esc(title)}</h3>{shown(here, name, title)}'
                f'{f"<p>{inline(here, note)}</p>" if note else ""}'
                f'<details><summary>The program, {n} lines</summary><pre class="code">{highlight(code)}</pre></details></article>')
    if kind == 'chips':
        return '<div class="chips">' + ''.join(
            f'<a href="{rel(here, INDEX[n])}"><code>{esc(n)}</code></a>' if n in INDEX else f'<span class="chip"><code>{esc(n)}</code></span>'
            for n in args) + '</div>'
    raise SystemExit(f'{here}: unknown directive {kind}')


def content_page(page):
    here = page.here
    sections, body = [], []
    for block in directives(page.body):
        if block[0] == 'md':
            body.append(md_blocks(here, block[1], sections))
        else:
            body.append(directive(here, block[1], block[2], block[3]))
    names = fiche_names(page)
    index = ''
    if page.section == 'reference' and names:
        index = '<div class="verbindex">' + ''.join(f'<a href="#{a}">{esc(n)}</a>' for n, a in names) + '</div>'
    hero = ''
    if page.meta.get('hero'):
        hero = shown(here, page.meta['hero'], page.title, 'hero')
    lead = f'<p class="chapo">{inline(here, page.meta["lead"])}</p>' if page.meta.get('lead') else ''
    head = (f'<h1>{esc(page.title)}</h1><div class="bande"></div>{lead}{index}{hero}')
    crumb = f'{dict(SECTIONS).get(page.section, "")} <span>›</span> {esc(page.nav)}' if page.section else esc(page.nav)
    title = 'sand3d' if here == 'index.html' else f'{page.title} · sand3d'
    return document(here, title, head + ''.join(body), sections, crumb)


def main():
    for page in PAGES:
        for name, anchor_id in fiche_names(page):
            if name in INDEX:
                raise SystemExit(f'{name} has two fiches: {INDEX[name]} and {page.here}#{anchor_id}')
            INDEX[name] = f'{page.here}#{anchor_id}'
    missing = set(PUBLIC_NAMES) - INDEX.keys()
    if missing:
        raise SystemExit('Public names without a fiche: ' + ', '.join(sorted(missing)))

    files = {page.here: content_page(page) for page in PAGES}
    for name in ('docs.css', 'docs.js', 'viewer.js'):
        files[f'assets/{name}'] = Path(__file__).with_name(name).read_text(encoding='utf-8')
    for name in LEGACY:
        text = (SITE / name).read_text(encoding='utf-8')
        # Keep legacy anchors and content, including historical version references in prose.
        files[name] = re.sub(r'(sand3d |<strong>Version</strong> )\d+\.\d+\.\d+(?:[-+][\w.-]+)?',
                             lambda match: match[1] + VERSION, text)

    for name, content in files.items():
        path = SITE / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    print(f'{len(PAGES)} documentation pages · {len(PUBLIC_NAMES)} API entries · sand3d {VERSION}')


if __name__ == '__main__':
    main()
