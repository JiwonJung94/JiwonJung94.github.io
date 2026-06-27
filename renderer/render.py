from __future__ import annotations
import datetime
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
TEMPLATES_DIR = Path(__file__).parent / 'templates'
PAGE_RE = re.compile('^(\\d{2})-(\\d{2})-(.+)\\.md$')
H1_RE = re.compile('^#\\s+(.+?)\\s*$', re.MULTILINE)
MD_EXTENSIONS = ['extra', 'sane_lists', 'toc', 'admonition']
LANG_NAMES = {'ko': '한국어', 'en': 'English', 'vi': 'Tiếng Việt', 'ja': '日本語', 'zh': '中文', 'fr': 'Français', 'es': 'Español'}
DEFAULT_SITE_NAME = {'ko': '라이브러리', 'en': 'Library', 'vi': 'Thư viện'}

def plaintext(md_text: str) -> str:
    html = markdown.markdown(md_text, extensions=MD_EXTENSIONS)
    return re.sub('\\s+', ' ', re.sub('<[^>]+>', ' ', html)).strip()

def summary(text: str, limit: int=160) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(' ', 1)[0].rstrip()
    return (cut or text[:limit]) + '…'

def _resolve_translated(value, locale: str, default_locale: str):
    if isinstance(value, dict):
        return value.get(locale, value.get(default_locale))
    return value

@dataclass
class Page:
    chapter: int
    section: int
    slug: str
    locale: str
    title: str
    body_md: str
    is_fallback: bool = False

    @property
    def out_name(self) -> str:
        return f'{self.chapter:02d}-{self.section:02d}-{self.slug}.html'

@dataclass
class Book:
    book_id: str
    src: Path
    meta: dict
    default_locale: str
    locales: list[str]
    pages: dict = field(default_factory=dict)

    def title(self, locale: str) -> str:
        return _resolve_translated(self.meta.get('title'), locale, self.default_locale)

    def description(self, locale: str):
        return _resolve_translated(self.meta.get('description'), locale, self.default_locale)

    def author(self, locale: str):
        return _resolve_translated(self.meta.get('author'), locale, self.default_locale)

    def cover(self, locale: str):
        return _resolve_translated(self.meta.get('cover'), locale, self.default_locale)

def load_book(book_dir: str | Path, book_id: str | None=None) -> Book:
    src = Path(book_dir).resolve()
    meta = yaml.safe_load((src / 'book.yml').read_text(encoding='utf-8')) or {}
    default_locale = meta.get('default_locale')
    locales = meta.get('locales') or []
    if not default_locale or default_locale not in locales:
        raise ValueError(f'{src}: default_locale가 비었거나 locales에 없음')
    book = Book(book_id=book_id or src.name, src=src, meta=meta, default_locale=default_locale, locales=list(locales))
    for locale in locales:
        loc_dir = src / 'pages' / locale
        if not loc_dir.is_dir():
            continue
        for md_file in sorted(loc_dir.glob('*.md')):
            m = PAGE_RE.match(md_file.name)
            if not m:
                continue
            (cc, ss, slug) = (int(m[1]), int(m[2]), m[3])
            text = md_file.read_text(encoding='utf-8')
            h1 = H1_RE.search(text)
            title = h1.group(1).strip() if h1 else slug
            book.pages[locale, cc, ss, slug] = Page(chapter=cc, section=ss, slug=slug, locale=locale, title=title, body_md=text)
    return book

def _ordered_slugs(book: Book) -> list[tuple[int, int, str]]:
    keys = {(cc, ss, slug) for (_loc, cc, ss, slug) in book.pages}
    return sorted(keys)

def _resolve_page(book: Book, locale: str, key: tuple[int, int, str]) -> Page | None:
    (cc, ss, slug) = key
    own = book.pages.get((locale, cc, ss, slug))
    if own:
        return own
    fallback = book.pages.get((book.default_locale, cc, ss, slug))
    if fallback is None:
        for loc in book.locales:
            fallback = book.pages.get((loc, cc, ss, slug))
            if fallback:
                break
    if fallback is None:
        return None
    return Page(chapter=cc, section=ss, slug=slug, locale=locale, title=fallback.title, body_md=fallback.body_md, is_fallback=True)

def _build_nav(resolved: list[Page]) -> list[dict]:
    chapters: dict[int, list[Page]] = {}
    for p in resolved:
        chapters.setdefault(p.chapter, []).append(p)
    nav = []
    for cc in sorted(chapters):
        ps = sorted(chapters[cc], key=lambda x: x.section)
        intro = next((p for p in ps if p.section == 0), ps[0])
        children = [{'label': p.title, 'href': p.out_name, 'key': (p.chapter, p.section, p.slug)} for p in ps if p is not intro]
        nav.append({'label': intro.title, 'href': intro.out_name, 'key': (intro.chapter, intro.section, intro.slug), 'children': children})
    return nav

def render_book(book_dir: str | Path, out_dir: str | Path, book_id: str | None=None, css: str | None=None, site_title=None, site_url: str | None=None, site_default_locale: str | None=None, views_url: str | None=None) -> Book:
    site_url = site_url.rstrip('/') if site_url else None
    book = load_book(book_dir, book_id)
    out_dir = Path(out_dir)
    book_out = out_dir / book.book_id
    book_out.mkdir(parents=True, exist_ok=True)
    if css is None:
        css_path = Path(__file__).parent / 'static' / 'style.css'
        css = css_path.read_text(encoding='utf-8') if css_path.exists() else ''
    js_path = Path(__file__).parent / 'static' / 'site.js'
    js = js_path.read_text(encoding='utf-8') if js_path.exists() else ''
    contact_email = book.meta.get('email')
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape(['html']))
    page_tmpl = env.get_template('page.html')
    redirect_tmpl = env.get_template('redirect.html')
    assets_src = book.src / 'assets'
    if assets_src.is_dir():
        shutil.copytree(assets_src, book_out / 'assets', dirs_exist_ok=True)
    slug_keys = _ordered_slugs(book)
    first_page_name = None
    for locale in book.locales:
        loc_out = book_out / locale
        loc_out.mkdir(parents=True, exist_ok=True)
        site_name = _resolve_translated(site_title, locale, book.default_locale)
        if not site_name:
            site_name = DEFAULT_SITE_NAME.get(locale, 'Library')
        author = book.author(locale)
        lic = book.meta.get('license')
        year = book.meta.get('year') or datetime.date.today().year
        copyright_text = f'© {year} {author}' if author else f'© {year}'
        if lic:
            copyright_text += f' · {lic}'
        resolved = [_resolve_page(book, locale, k) for k in slug_keys]
        resolved = [p for p in resolved if p is not None]
        nav = _build_nav(resolved)
        for (idx, page) in enumerate(resolved):
            prev_p = resolved[idx - 1] if idx > 0 else None
            next_p = resolved[idx + 1] if idx < len(resolved) - 1 else None
            content_html = markdown.markdown(page.body_md, extensions=MD_EXTENSIONS)
            real_locales = [lc for lc in book.locales if (lc, page.chapter, page.section, page.slug) in book.pages]
            pref = next((c for c in (site_default_locale, book.default_locale) if c in real_locales), real_locales[0] if real_locales else locale)
            body_wo_h1 = H1_RE.sub('', page.body_md, count=1)
            meta_description = summary(plaintext(body_wo_h1)) or book.description(locale) or ''

            def _abs(lc, name=page.out_name):
                return f'{site_url}/{book.book_id}/{lc}/{name}' if site_url else None
            robots_noindex = page.is_fallback
            canonical = _abs(pref if page.is_fallback else locale)
            (hreflang, hreflang_xdefault) = ([], None)
            if site_url and (not page.is_fallback):
                hreflang = [{'lang': lc, 'href': _abs(lc)} for lc in real_locales]
                hreflang_xdefault = _abs(pref)
            cover_name = book.cover(locale)
            og_image = f'{site_url}/{book.book_id}/{cover_name}' if site_url and cover_name and (book_out / cover_name).is_file() else None
            og = {'title': page.title, 'description': meta_description, 'url': canonical, 'site_name': book.title(locale), 'locale': locale, 'image': og_image}
            views_json = json.dumps({'url': views_url, 'book': book.book_id, 'slug': page.out_name[:-5], 'lang': locale, 'locales': book.locales}, ensure_ascii=False) if views_url else None
            locale_options = []
            for lc in book.locales:
                real = (lc, page.chapter, page.section, page.slug) in book.pages
                locale_options.append({'code': lc, 'label': LANG_NAMES.get(lc, lc.upper()), 'href': f'../{lc}/{page.out_name}', 'active': lc == locale, 'real': real})
            jsonld = None
            if site_url:
                _author = book.author(locale)
                _btitle = book.title(locale)
                _year = book.meta.get('year') or datetime.date.today().year
                _book = {'@type': 'Book', 'name': _btitle, 'inLanguage': locale}
                _article = {'@type': 'Article', 'headline': page.title, 'inLanguage': locale, 'url': canonical, 'datePublished': str(_year), 'isPartOf': _book, 'publisher': {'@type': 'Organization', 'name': site_name, 'logo': {'@type': 'ImageObject', 'url': f'{site_url}/icon-512.png'}}}
                if _author:
                    _person = {'@type': 'Person', 'name': _author}
                    _article['author'] = _person
                    _book['author'] = _person
                _crumbs = [{'@type': 'ListItem', 'position': 1, 'name': site_name, 'item': f'{site_url}/'}, {'@type': 'ListItem', 'position': 2, 'name': _btitle, 'item': f'{site_url}/{book.book_id}/'}, {'@type': 'ListItem', 'position': 3, 'name': page.title}]
                jsonld = json.dumps({'@context': 'https://schema.org', '@graph': [_article, {'@type': 'BreadcrumbList', 'itemListElement': _crumbs}]}, ensure_ascii=False).replace('<', '\\u003c')
            html = page_tmpl.render(book_title=book.title(locale), page_title=page.title, lang=locale, is_fallback=page.is_fallback, default_locale=book.default_locale, content_html=content_html, nav=[{**c, 'active': c['key'] == (page.chapter, page.section, page.slug), 'children': [{**ch, 'active': ch['key'] == (page.chapter, page.section, page.slug)} for ch in c['children']]} for c in nav], locale_options=locale_options, prev={'href': prev_p.out_name, 'label': prev_p.title} if prev_p else None, next={'href': next_p.out_name, 'label': next_p.title} if next_p else None, site_home='../../index.html', site_name=site_name, copyright=copyright_text, contact_email=contact_email, meta_description=meta_description, robots_noindex=robots_noindex, canonical=canonical, hreflang=hreflang, hreflang_xdefault=hreflang_xdefault, og=og, views_url=views_url, views_json=views_json, jsonld=jsonld, css=css, js=js)
            (loc_out / page.out_name).write_text(html, encoding='utf-8')
            if locale == book.default_locale and first_page_name is None:
                first_page_name = page.out_name
    if first_page_name:
        target = f'{book.default_locale}/{first_page_name}'
        (book_out / 'index.html').write_text(redirect_tmpl.render(target=target), encoding='utf-8')
    return book

def _main():
    import argparse
    ap = argparse.ArgumentParser(description='book-repo → 정적 HTML 렌더')
    ap.add_argument('book_dir', help='책 저장소 경로 (book.yml 있는 곳)')
    ap.add_argument('-o', '--out', default='_site', help='출력 디렉터리 (기본 _site)')
    ap.add_argument('--id', default=None, help='book_id (기본: 디렉터리명)')
    args = ap.parse_args()
    book = render_book(args.book_dir, args.out, book_id=args.id)
    print(f"렌더 완료: {args.out}/{book.book_id}/  (locales: {', '.join(book.locales)})")
if __name__ == '__main__':
    _main()
