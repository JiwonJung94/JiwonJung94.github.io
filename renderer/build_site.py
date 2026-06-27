from __future__ import annotations
import argparse
import datetime
import json
import shutil
import sys
from pathlib import Path
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from render import LANG_NAMES, TEMPLATES_DIR, _ordered_slugs, git_date, plaintext, render_book
STATIC_CSS = Path(__file__).parent / 'static' / 'style.css'
STATIC_JS = Path(__file__).parent / 'static' / 'site.js'

def _discover(inputs: list[str]) -> list[Path]:
    books: list[Path] = []
    for item in inputs:
        p = Path(item).resolve()
        if (p / 'book.yml').is_file():
            books.append(p)
        elif p.is_dir():
            for child in sorted(p.iterdir()):
                if (child / 'book.yml').is_file():
                    books.append(child)
    (seen, out) = (set(), [])
    for b in books:
        if b not in seen:
            seen.add(b)
            out.append(b)
    return out

def _as_map(value, langs: list[str], default: str) -> dict:
    if isinstance(value, dict):
        return {l: value[l] for l in langs if value.get(l)} or {default: ''}
    return {default: value or ''}

def build(inputs: list[str], out_dir: str, site_title: str, site_subtitle: str='', footer: str='', config: str='') -> int:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    css = STATIC_CSS.read_text(encoding='utf-8') if STATIC_CSS.exists() else ''
    js = STATIC_JS.read_text(encoding='utf-8') if STATIC_JS.exists() else ''
    book_dirs = _discover(inputs)
    if not book_dirs:
        print('발견된 책이 없습니다 (book.yml 보유 디렉터리 없음).', file=sys.stderr)
        return 1
    cfg = {}
    if config and Path(config).is_file():
        cfg = yaml.safe_load(Path(config).read_text(encoding='utf-8')) or {}
    cfg_title = cfg.get('title', site_title)
    cfg_subtitle = cfg.get('subtitle', site_subtitle)
    site_url = (cfg.get('url') or '').rstrip('/') or None
    cfg_default = cfg.get('default_locale')
    views_url = (cfg.get('views_url') or '').rstrip('/') or None
    verification = cfg.get('verification') or {}
    analytics_cf = (cfg.get('analytics') or {}).get('cloudflare')
    cards = []
    site_books = []
    index_books = []
    site_langs = []
    for bdir in book_dirs:
        try:
            book = render_book(bdir, out, book_id=bdir.name, css=css, site_title=cfg_title, site_url=site_url, site_default_locale=cfg_default, views_url=views_url, verification=verification, analytics_cf=analytics_cf)
        except Exception as e:
            print(f'[건너뜀] {bdir.name}: {e}', file=sys.stderr)
            continue
        dl = book.default_locale
        bid = book.book_id
        for lc in book.locales:
            if lc not in site_langs:
                site_langs.append(lc)

        def _map(getter):
            m = {}
            for lc in book.locales:
                v = getter(lc)
                if v:
                    m[lc] = v
            m.setdefault(dl, getter(dl) or '')
            return m
        slug_keys = _ordered_slugs(book)
        first_slug = slug_keys[0] if slug_keys else None
        first_name = f'{first_slug[0]:02d}-{first_slug[1]:02d}-{first_slug[2]}.html' if first_slug else 'index.html'
        cover = book.cover(dl)
        cover_rel = cover if cover and (out / bid / cover).is_file() else None
        title_map = _map(book.title)
        desc_map = _map(book.description)
        author_map = _map(book.author)
        lic = book.meta.get('license')
        yr = book.meta.get('year') or datetime.date.today().year
        copyright_map = {}
        for lc in book.locales:
            au = author_map.get(lc) or author_map.get(dl) or ''
            c = f'© {yr} {au}' if au else f'© {yr}'
            if lic:
                c += f' · {lic}'
            copyright_map[lc] = c
        b_email = book.meta.get('email')
        site_books.append({'id': bid, 'default': dl, 'locales': book.locales, 'first': first_name, 'cover': cover_rel, 'title': title_map, 'description': desc_map, 'author': author_map, 'copyright': copyright_map, 'contact': b_email})
        idx_pages = []
        for (cc, ss, slug) in slug_keys:
            (t_map, x_map, d_map) = ({}, {}, {})
            for lc in book.locales:
                pg = book.pages.get((lc, cc, ss, slug))
                if pg:
                    t_map[lc] = pg.title
                    x_map[lc] = plaintext(pg.body_md)
                    _d = git_date(book.src / 'pages' / lc / f'{cc:02d}-{ss:02d}-{slug}.md')
                    if _d:
                        d_map[lc] = _d
            idx_pages.append({'slug': f'{cc:02d}-{ss:02d}-{slug}', 'title': t_map, 'text': x_map, 'dates': d_map})
        index_books.append({'id': bid, 'default': dl, 'locales': book.locales, 'title': title_map, 'description': desc_map, 'pages': idx_pages})
        print(f"  ✓ {bid}  ({', '.join(book.locales)})")
    cfg_default = cfg.get('default_locale')
    site_default = cfg_default if cfg_default in site_langs else site_langs[0] if site_langs else 'ko'
    title_map = _as_map(cfg_title, site_langs, site_default)
    subtitle_map = _as_map(cfg_subtitle, site_langs, site_default)

    def _res(m, b):
        return m.get(site_default) or m.get(b['default']) or ''
    for b in site_books:
        loc = site_default if site_default in b['locales'] else b['default']
        cards.append({'id': b['id'], 'href': f"{b['id']}/{loc}/{b['first']}", 'title': _res(b['title'], b) or b['id'], 'author': _res(b['author'], b), 'description': _res(b['description'], b), 'cover': f"{b['id']}/{b['cover']}" if b['cover'] else None, 'locales': b['locales'], 'copyright': _res(b['copyright'], b), 'contact': b['contact']})
    home_jsonld = None
    if site_url:
        _items = []
        for (_i, _b) in enumerate(site_books, 1):
            _name = _b['title'].get(site_default) or _b['title'].get(_b['default']) or _b['id']
            _bk = {'@type': 'Book', 'name': _name, 'url': f"{site_url}/{_b['id']}/", 'inLanguage': _b['locales']}
            _au = _b['author'].get(site_default) or _b['author'].get(_b['default'])
            if _au:
                _bk['author'] = {'@type': 'Person', 'name': _au}
            _items.append({'@type': 'ListItem', 'position': _i, 'item': _bk})
        _org = {'@type': 'Organization', 'name': title_map.get(site_default, 'Library'), 'url': f'{site_url}/', 'logo': {'@type': 'ImageObject', 'url': f'{site_url}/icon-512.png'}}
        _graph = [_org, {'@type': 'WebSite', 'name': title_map.get(site_default, 'Library'), 'url': f'{site_url}/', 'inLanguage': site_langs, 'publisher': {'@type': 'Organization', 'name': title_map.get(site_default, 'Library')}}, {'@type': 'CollectionPage', 'name': title_map.get(site_default, 'Library'), 'url': f'{site_url}/', 'mainEntity': {'@type': 'ItemList', 'itemListElement': _items}}]
        home_jsonld = json.dumps({'@context': 'https://schema.org', '@graph': _graph}, ensure_ascii=False).replace('<', '\\u003c')
    site_json = {'books': site_books, 'langs': site_langs, 'langNames': {lc: LANG_NAMES.get(lc, lc.upper()) for lc in site_langs}, 'defaultLang': site_default, 'title': title_map, 'subtitle': subtitle_map, 'viewsUrl': views_url}
    (out / 'search-index.json').write_text(json.dumps({'books': index_books}, ensure_ascii=False), encoding='utf-8')
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape(['html']))
    index_html = env.get_template('index.html').render(site_title=title_map.get(site_default, ''), site_subtitle=subtitle_map.get(site_default, ''), footer=footer or f'{len(cards)}권', default_locale=site_default, css=css, js=js, books=cards, views_url=views_url, jsonld=home_jsonld, verification=verification, analytics_cf=analytics_cf, meta_description=subtitle_map.get(site_default, ''), canonical=f'{site_url}/' if site_url else None, og={'title': title_map.get(site_default, ''), 'description': subtitle_map.get(site_default, ''), 'url': f'{site_url}/' if site_url else None}, site_json=json.dumps(site_json, ensure_ascii=False))
    (out / 'index.html').write_text(index_html, encoding='utf-8')
    nf_books = [{'id': b['id'], 'default': b['default'], 'locales': b['locales'], 'slugs': [p['slug'] for p in b['pages']]} for b in index_books]
    nf_html = env.get_template('404.html').render(data=json.dumps({'books': nf_books}, ensure_ascii=False))
    (out / '404.html').write_text(nf_html, encoding='utf-8')
    robots = 'User-agent: *\nAllow: /\n'
    if site_url:
        robots += f'Sitemap: {site_url}/sitemap.xml\n'

        def _xml(s):
            return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        rows = [f'  <url><loc>{site_url}/</loc></url>']
        for b in index_books:
            bid = b['id']
            blocs = b['locales']
            land_alts = ''.join(('<xhtml:link rel="alternate" hreflang="%s" href="%s"/>' % (lc, _xml('%s/%s/%s/' % (site_url, bid, lc))) for lc in blocs))
            for lc in blocs:
                rows.append('  <url><loc>%s</loc>%s</url>' % (_xml('%s/%s/%s/' % (site_url, bid, lc)), land_alts))
            for p in b['pages']:
                (slug, real) = (p['slug'], list(p['title'].keys()))
                alts = ''.join(('<xhtml:link rel="alternate" hreflang="%s" href="%s"/>' % (lc, _xml('%s/%s/%s/%s.html' % (site_url, bid, lc, slug))) for lc in real))
                for lc in real:
                    loc = _xml('%s/%s/%s/%s.html' % (site_url, bid, lc, slug))
                    lm = p.get('dates', {}).get(lc)
                    lmtag = '<lastmod>%s</lastmod>' % lm if lm else ''
                    rows.append('  <url><loc>%s</loc>%s%s</url>' % (loc, lmtag, alts))
        sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n' + '\n'.join(rows) + '\n</urlset>\n'
        (out / 'sitemap.xml').write_text(sitemap, encoding='utf-8')
    (out / 'robots.txt').write_text(robots, encoding='utf-8')
    assets_dir = (Path(config).parent if config else Path('.')) / 'site-assets'
    if assets_dir.is_dir():
        for f in assets_dir.iterdir():
            if f.is_file():
                shutil.copy2(f, out / f.name)
    manifest = {'name': title_map.get(site_default, 'Library'), 'short_name': title_map.get(site_default, 'Library'), 'start_url': '/', 'display': 'standalone', 'background_color': '#fbfaf7', 'theme_color': '#8a5a2b', 'icons': [{'src': '/icon-192.png', 'sizes': '192x192', 'type': 'image/png'}, {'src': '/icon-512.png', 'sizes': '512x512', 'type': 'image/png'}, {'src': '/icon-512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable'}]}
    (out / 'site.webmanifest').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
    (out / '.nojekyll').write_text('', encoding='utf-8')
    print(f'\n사이트 빌드 완료: {out}/  (책 {len(cards)}권)')
    return 0

def main():
    ap = argparse.ArgumentParser(description='여러 book-repo → 통합 Pages 사이트')
    ap.add_argument('inputs', nargs='+', help='책 디렉터리들, 또는 그것들을 담은 컨테이너 디렉터리')
    ap.add_argument('-o', '--out', default='_site')
    ap.add_argument('--title', default='서가')
    ap.add_argument('--subtitle', default='')
    ap.add_argument('--footer', default='')
    ap.add_argument('--config', default='', help='사이트 title/subtitle locale 맵을 담은 yaml')
    args = ap.parse_args()
    sys.exit(build(args.inputs, args.out, args.title, args.subtitle, args.footer, args.config))
if __name__ == '__main__':
    main()
