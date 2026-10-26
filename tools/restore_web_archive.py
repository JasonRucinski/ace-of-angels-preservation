#!/usr/bin/env python3
"""Recover a private, read-only mirror from the documented Wayback captures.

Raw responses and the resumable ledger stay in ignored wb/site-archive/.
Only build/ is deployed. No original scripts or form submissions are enabled.
"""
import argparse
import hashlib
import html
import http.client
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse as U

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / 'wb/site-archive'
BUILD = STORE / 'build'
HOSTS = {'aceofangels.com', 'flyingrockllc.com', 'aoahost.com'}
BLOCK_EXT = {'.exe', '.zip', '.rar', '.7z', '.bin', '.aoa', '.odb', '.mp3', '.wmv', '.avi', '.mov', '.mpg', '.mpeg', '.dll', '.cab', '.iso'}
CSS_URL = re.compile(r'url\(\s*[\"\']?([^\)\"\']+)[\"\']?\s*\)', re.I)
CAPTURE = re.compile(r'https?://web\.archive\.org/web/(\d{14})[a-z_]*/(https?://[^\s<>\"\']+)')


def canonical(url):
    url = html.unescape(url.strip())
    m = CAPTURE.match(url)
    if m:
        url = m[2]
    p = U.urlsplit(url)
    host = (p.hostname or '').lower().removeprefix('www.')
    if host not in HOSTS:
        return None
    path = p.path or '/'
    if Path(path).suffix.lower() in BLOCK_EXT:
        return None
    pairs = U.parse_qsl(p.query, keep_blank_values=True)
    # These identify a visitor/session, not a different archived document.
    pairs = [(k, v) for k, v in pairs if k.lower() not in {'sid', 'phpsessid', 'session', 'ver', 's', 'replytocom'}]
    if any(k.lower() in {'feed', 'author', 'm', 'cat', 'search', 'new', 'reply', 'edit'} for k, v in pairs):
        return None
    if re.search(r'/(wp-admin|wp-login|xmlrpc|wp-json|search|register|login|profile|postings?|ubbmisc|archive|post|edit|sendpwd|bb-login|bb-register)([./?]|$)', path, re.I):
        return None
    if 'openarticle.pl' in path.lower() and not any(k == 'articlenumber' and v.isdigit() for k, v in pairs):
        return None
    if any(k.lower() == 'action' and v.lower() not in {'intro', 'topics', 'display', 'show'} for k, v in pairs):
        return None
    return U.urlunsplit(('http', host, path, U.urlencode(sorted(pairs)), ''))


def kind_for(url, mime=''):
    ext = Path(U.urlsplit(url).path).suffix.lower()
    if 'css' in mime or ext == '.css' or 'style.php' in url or 'css.php' in url:
        return 'css'
    if mime.startswith('image/') or ext in {'.gif', '.jpg', '.jpeg', '.png', '.bmp', '.ico', '.svg', '.webp'}:
        return 'asset'
    if ext in {'.js', '.swf', '.class', '.jar'}:
        return 'skip'
    if ext == '.pdf':
        return 'asset'
    return 'page'


def local_path(url, kind):
    digest = hashlib.sha256(url.encode()).hexdigest()[:24]
    ext = '.html' if kind == 'page' else '.css' if kind == 'css' else Path(U.urlsplit(url).path).suffix.lower()
    if not re.fullmatch(r'\.[a-z0-9]{1,5}', ext or ''):
        ext = '.dat'
    return '/archive/' + digest + ext


class Mirror:
    def __init__(self, pause=4.0):
        STORE.mkdir(parents=True, exist_ok=True)
        (STORE / 'raw').mkdir(exist_ok=True)
        self.ledger_path = STORE / 'ledger.json'
        self.rows = json.loads(self.ledger_path.read_text('utf-8')) if self.ledger_path.exists() else {}
        self.last_request = 0
        self.pause = pause
        self.connection = http.client.HTTPSConnection('web.archive.org', timeout=35)

    def save(self):
        tmp = self.ledger_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.rows, indent=2, ensure_ascii=False), 'utf-8')
        tmp.replace(self.ledger_path)

    def enqueue(self, url, timestamp, kind=None, title=None, base=None, discovered=False):
        if base:
            url = U.urljoin(base, html.unescape(url))
        match = CAPTURE.match(url)
        if match:
            timestamp, url = match[1], match[2]
        key = canonical(url)
        if not key:
            return None
        kind = kind or kind_for(key)
        if kind == 'skip':
            return None
        if key not in self.rows:
            self.rows[key] = {'url': key, 'original': url, 'timestamp': timestamp, 'kind': kind, 'state': 'pending'}
            if discovered and U.urlsplit(key).hostname in {'aceofangels.com', 'flyingrockllc.com'}:
                self.rows[key].update(state='missing', error='No successful capture in the selected CDX URL inventory')
        if title:
            self.rows[key]['label'] = title
        return key

    def seed(self):
        handoff = (ROOT / 'docs' / 'history' / '2026-10-20-research-handoff.txt').read_text('utf-8')
        for line in handoff.splitlines():
            for m in CAPTURE.finditer(line):
                self.enqueue(m[2].rstrip(').,;'), m[1])
        for url, ts, title in [
            ('http://www.aceofangels.com/', '20110128084333', 'Official site (2009–2011)'),
            ('http://www.aceofangels.com/', '20010127072200', 'Official site (2009–2011)'),
            ('http://www.aceofangels.com/forum/', '20090704184718', 'Later forums'),
            ('http://www.flyingrockllc.com/ubb/Ultimate.cgi?action=intro', '20010718043717', 'Original forums'),
            ('http://www.flyingrockllc.com/', '20010718043717', 'Original Flying Rock site'),
        ]:
            self.enqueue(url, ts, title=title)
        self.save()

    def import_indexes(self):
        for name in ['wayback-site-index.json', 'wayback-forum-index.json']:
            source = ROOT / 'work' / name
            if not source.exists():
                continue
            rows = json.loads(source.read_text('utf-8'))[1:]
            for timestamp, original, mime, status, digest, length in rows:
                # The game-era site ends in the 2011 snapshots. Later captures
                # include a reset WordPress install and domain-parking redirects.
                if timestamp > '20111231235959':
                    continue
                if mime not in {'text/html', 'text/css', 'application/pdf'} and not mime.startswith('image/'):
                    continue
                key = self.enqueue(original, timestamp, kind_for(original, mime))
                if key:
                    self.rows[key].setdefault('cdx_digest', digest)
                    if self.rows[key]['state'] != 'ok':
                        self.rows[key].update(timestamp=timestamp, original=original, cdx_digest=digest)
        self.save()

    def import_forum_versions(self):
        source = ROOT / 'work/wayback-forum-versions.json'
        if not source.exists():
            return
        best = {}
        for row in json.loads(source.read_text('utf-8'))[1:]:
            key = canonical(row[1])
            if key and row[0] <= '20111231235959' and (key not in best or (int(row[5]), row[0]) > (int(best[key][5]), best[key][0])):
                best[key] = row
        changed = 0
        for key, (timestamp, original, mime, status, digest, length) in best.items():
            current = self.rows.get(key)
            if current and current.get('cdx_digest') != digest:
                if current['state'] == 'ok':
                    current['fallback'] = dict(current)
                current.update(timestamp=timestamp, original=original, cdx_digest=digest, state='pending')
                changed += 1
        self.save()
        print(f'{changed} forum URLs queued for a larger indexed capture.', flush=True)

    def fetch(self, row):
        time.sleep(max(0, self.pause - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        replay = f'https://web.archive.org/web/{row["timestamp"]}id_/{row["original"]}'
        try:
            # Reuse one HTTPS connection; thousands of new TLS connections are
            # unnecessary for this sequential, paced crawl.
            for redirect in range(10):
                parsed = U.urlsplit(replay)
                if parsed.hostname != 'web.archive.org':
                    raise ValueError('Replay redirected away from the archive')
                self.connection.request('GET', U.urlunsplit(('', '', parsed.path, parsed.query, '')), headers={'User-Agent': 'AceOfAngels-personal-preservation/1.0', 'Connection': 'keep-alive'})
                response = self.connection.getresponse()
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.headers.get('Location', '')
                    response.read()
                    target = U.urlsplit(U.urljoin(replay, location))
                    replay = U.urlunsplit(target._replace(scheme='https'))
                    continue
                if response.status != 200:
                    response.read()
                    raise urllib.error.HTTPError(replay, response.status, response.reason, response.headers, None)
                body_limit = (64 if row['kind'] == 'page' and 'players/scores/by_names.html' in row['original'] else 12) * 1024 * 1024
                body = response.read(body_limit + 1)
                if len(body) > body_limit:
                    self.connection.close()
                    raise ValueError(f'Capture exceeds {body_limit // (1024 * 1024)} MiB recovery limit')
                mime = response.headers.get_content_type()
                if b'Internet Archive services are temporarily offline' in body or b'Wayback Machine has not archived that URL' in body:
                    raise ValueError('Archive error page')
                actual = CAPTURE.match(replay)
                if actual:
                    row['timestamp'] = actual[1]
                    if actual[1] > '20111231235959':
                        raise ValueError('Replay falls outside the original game-era website (through 2011)')
                row.update(mime=mime, replay=replay, bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), state='ok')
                if row['kind'] == 'page' and mime not in {'text/html', 'application/xhtml+xml', 'text/plain'}:
                    row['kind'] = kind_for(row['url'], mime)
                raw = STORE / 'raw' / row['sha256']
                raw.write_bytes(body)
                row['raw'] = str(raw.relative_to(STORE)).replace('\\', '/')
                charset = response.headers.get_content_charset() or ('utf-8' if b'charset=UTF-8' in body[:4000] else 'windows-1252')
                row['charset'] = charset
                break
            else:
                raise ValueError('Too many archive redirects')
        except urllib.error.HTTPError as error:
            row.update(state='missing', error=f'HTTP {error.code}')
            if error.code in {429, 503}:
                print(f'Archive returned {error.code}; backing off for 60 seconds.', flush=True)
                time.sleep(60)
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as error:
            self.connection.close()
            self.connection = http.client.HTTPSConnection('web.archive.org', timeout=35)
            row.update(state='pending', error=str(error)[:240])
            self.save()
            print('Connection interrupted; preserving the queue. Retry after archive service recovers.', flush=True)
            return False
        except ValueError as error:
            row.update(state='missing', error=str(error)[:240])
        if row['state'] == 'missing' and row.get('fallback'):
            failure = row['error']
            previous = row.pop('fallback')
            row.clear()
            row.update(previous, upgrade_error=failure)
        elif row['state'] == 'ok':
            row.pop('fallback', None)
            row.pop('error', None)
        if row['state'] == 'ok' and row['kind'] in {'page', 'css'}:
            self.render(row, discover=True)
        self.save()
        return True

    def rewrite(self, value, row, kind=None, discover=False):
        if not value or value.startswith(('#', 'data:')):
            return value
        if value.lower().startswith(('javascript:', 'mailto:', 'tel:')):
            return '#archive-read-only'
        url = U.urljoin(row['original'], html.unescape(value))
        key = canonical(url)
        if not key:
            return '/unavailable.html#' + U.quote(url, safe='')
        if discover:
            self.enqueue(url, row['timestamp'], kind=kind, discovered=True)
        target = self.rows.get(key)
        if target and target['state'] == 'ok':
            return local_path(key, target['kind']) + ('#' + U.urlsplit(value).fragment if U.urlsplit(value).fragment else '')
        return '/unavailable.html#' + U.quote(url, safe='')

    def css(self, value, row, discover=False):
        return CSS_URL.sub(lambda m: 'url("' + self.rewrite(m[1], row, 'asset', discover) + '")', value)

    def render(self, row, discover=False):
        raw = (STORE / row['raw']).read_bytes()
        try:
            value = raw.decode(row.get('charset', 'utf-8'), errors='replace')
        except LookupError:
            value = raw.decode('utf-8', errors='replace')
        if row['kind'] == 'css':
            return self.css(value, row, discover)
        parser = ArchiveHTML(self, row, discover)
        parser.feed(value)
        parser.close()
        row['title'] = html.unescape(''.join(parser.title)).strip() or row.get('label', row['url'])
        if 'openarticle.pl' in row['url']:
            headings = re.findall(r'<font\b[^>]*\bclass\s*=\s*[\"\']?head[\"\']?[^>]*>(.*?)</font\s*>', value, re.I | re.S)
            row['title'] = 'Untitled captured article ' + dict(U.parse_qsl(U.urlsplit(row['url']).query)).get('articlenumber', '')
            for heading in headings:
                headline = ' '.join(html.unescape(re.sub(r'<[^>]+>', '', heading)).split())
                if headline and headline.casefold() not in {'main menu', 'past articles'}:
                    row['title'] = headline
                    break
        return ''.join(parser.out)

    def recover(self, limit):
        # Finish required styles/images before advancing to the next page.
        total = 0
        connection_failures = 0
        while total < limit:
            if (STORE / 'STOP').exists():
                break
            pending = [r for r in self.rows.values() if r['state'] == 'pending']
            if not pending:
                break
            row = min(pending, key=lambda r: 0 if r['kind'] == 'css' else 1 if r['kind'] == 'asset' else 2 if ('/ubb/' in r['url'].lower() or '/forum/' in r['url'] or '/bbs/' in r['url'] or 'page_id=' in r['url']) else 4 if 'openarticle.pl' in r['url'] else 3)
            if self.fetch(row) is False:
                connection_failures += 1
                if connection_failures >= 3:
                    break
                print('Backing off for 60 seconds before retrying this capture.', flush=True)
                time.sleep(60)
                continue
            connection_failures = 0
            total += 1
            print(f'{total}: {row["state"]} {row["kind"]} {row["url"]} ({sum(r["state"] == "pending" for r in self.rows.values())} pending)', flush=True)
            if total % 50 == 0:
                self.build()
        self.save()

    def build(self):
        (BUILD / 'archive').mkdir(parents=True, exist_ok=True)
        pages = []
        for key, row in list(self.rows.items()):
            if row['state'] != 'ok':
                continue
            target = BUILD / local_path(key, row['kind']).lstrip('/')
            if row['kind'] in {'page', 'css'}:
                target.write_text(self.render(row), 'utf-8')
            else:
                target.write_bytes((STORE / row['raw']).read_bytes())
            if row['kind'] == 'page':
                pages.append({'title': row['title'], 'path': local_path(key, row['kind']), 'url': key, 'capture': row['timestamp'], 'forum': bool(re.search(r'/forum|/ubb|/bbs|/(?:cgi-local|cgi-bin)/(?:ultimate|forumdisplay)', key, re.I))})
        pages.sort(key=lambda p: (not p['forum'], p['title'].lower()))
        counts = {s: sum(r['state'] == s for r in self.rows.values()) for s in ['ok', 'missing', 'pending']}
        (BUILD / 'catalog.json').write_text(json.dumps(pages, ensure_ascii=False), 'utf-8')
        (BUILD / 'archive-ui.css').write_text(UI_CSS, 'utf-8')
        (BUILD / 'archive-ui.js').write_text(UI_JS, 'utf-8')
        (BUILD / 'missing.js').write_text("const el=document.getElementById('original-url');try{el.textContent=decodeURIComponent(location.hash.slice(1));}catch{el.textContent='Invalid source URL';}", 'utf-8')
        favicon = self.rows.get('http://aceofangels.com/favicon.ico')
        if favicon and favicon['state'] == 'ok':
            (BUILD / 'favicon.ico').write_bytes((STORE / favicon['raw']).read_bytes())
        featured = []
        for key, label in [('http://aceofangels.com/frames/ffgame.html', 'Classic website'), ('http://aceofangels.com/', 'Later website'), ('http://aceofangels.com/?page_id=346', 'The Known Sphere'), ('http://aceofangels.com/?page_id=111', 'Forgotten Suns')]:
            if key in self.rows and self.rows[key]['state'] == 'ok':
                featured.append('<a href="' + local_path(key, 'page') + '">' + label + '</a>')
        featured.append('<a href="#pages" id="browse-forums">Browse forum threads</a>')
        index = INDEX.replace('FEATURED', ' · '.join(featured)).replace('COUNTS', f'{len(pages)} recovered pages · {counts["missing"]} unavailable URLs · {counts["pending"]} awaiting recovery')
        (BUILD / 'index.html').write_text(index, 'utf-8')
        (BUILD / 'unavailable.html').write_text(UNAVAILABLE, 'utf-8')
        (BUILD / 'robots.txt').write_text('User-agent: *\nDisallow: /\n', 'utf-8')
        (BUILD / 'vercel.json').write_text(json.dumps({'framework': None, 'headers': [{'source': '/(.*)', 'headers': [
            {'key': 'X-Robots-Tag', 'value': 'noindex, nofollow, noarchive'},
            {'key': 'Content-Security-Policy', 'value': "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; object-src 'none'; form-action 'none'; base-uri 'none'; frame-src 'self'; frame-ancestors 'self'"},
            {'key': 'Referrer-Policy', 'value': 'no-referrer'},
            {'key': 'X-Content-Type-Options', 'value': 'nosniff'},
        ]}]}), 'utf-8')
        self.save()
        sizes = [p.stat().st_size for p in BUILD.rglob('*') if p.is_file() and '.vercel' not in p.relative_to(BUILD).parts]
        summary = {'pages': len(pages), 'forum_pages': sum(p['forum'] for p in pages), 'states': counts, 'deploy_files': len(sizes), 'deploy_bytes': sum(sizes), 'raw_bytes': sum(r.get('bytes', 0) for r in self.rows.values() if r['state'] == 'ok')}
        (STORE / 'summary.json').write_text(json.dumps(summary, indent=2), 'utf-8')
        print(json.dumps(summary, indent=2), flush=True)


class ArchiveHTML(HTMLParser):
    def __init__(self, mirror, row, discover):
        super().__init__(convert_charrefs=False)
        self.mirror, self.row, self.discover = mirror, row, discover
        self.out, self.title = [], []
        self.skip = 0
        self.in_title = False
        self.in_style = False
        self.base_row = row
        self.default_target = None

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'object', 'applet'}:
            self.skip += 1
            return
        if self.skip:
            return
        a = dict(attrs)
        if tag == 'base':
            if a.get('href'):
                self.base_row = {**self.row, 'original': U.urljoin(self.row['original'], a['href'])}
            if a.get('target'):
                self.default_target = a['target']
            return
        if tag == 'embed' or (tag == 'meta' and a.get('http-equiv', '').lower() == 'refresh'):
            return
        if tag == 'link' and a.get('rel', '').lower() not in {'stylesheet', 'icon', 'shortcut icon'}:
            return
        if tag == 'meta' and ('charset' in a or a.get('http-equiv', '').lower() == 'content-type'):
            self.out.append('<meta charset="utf-8">')
            return
        cleaned = []
        for k, v in attrs:
            if k.startswith('on') or k in {'action', 'formaction', 'srcset', 'integrity', 'nonce', 'ping'}:
                continue
            if v is not None and k in {'href', 'src', 'background', 'poster', 'data'}:
                resource = 'css' if tag == 'link' and a.get('rel', '').lower() == 'stylesheet' else 'asset' if tag in {'img', 'body', 'td', 'table', 'input', 'source'} or k == 'background' else None
                v = self.mirror.rewrite(v, self.base_row, resource, self.discover)
            elif k == 'style' and v:
                v = self.mirror.css(v, self.base_row, self.discover)
            cleaned.append(k if v is None else k + '="' + html.escape(v, quote=True) + '"')
        if tag in {'button', 'input', 'select', 'textarea'}:
            cleaned.append('disabled')
        if tag == 'a' and 'target' not in a and self.default_target:
            cleaned.append('target="' + html.escape(self.default_target, quote=True) + '"')
        self.out.append('<' + tag + (' ' + ' '.join(cleaned) if cleaned else '') + '>')
        if tag == 'head':
            self.out.append('<meta charset="utf-8"><link rel="stylesheet" href="/archive-ui.css">')
        if tag == 'body':
            source = f'https://web.archive.org/web/{self.row["timestamp"]}/{self.row["original"]}'
            self.out.append('<aside class="archive-banner" id="archive-read-only"><a href="/" target="_top">Archive index</a> · Read-only capture · ' + self.row['timestamp'][:4] + '-' + self.row['timestamp'][4:6] + '-' + self.row['timestamp'][6:8] + ' · <a target="_top" href="' + html.escape(source, quote=True) + '">Wayback source</a></aside>')
        self.in_title = tag == 'title' or self.in_title
        self.in_style = tag == 'style' or self.in_style

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in {'script', 'object', 'applet'}:
            self.skip = max(0, self.skip - 1)
            return
        if not self.skip:
            self.out.append('</' + tag + '>')
        if tag == 'title':
            self.in_title = False
        if tag == 'style':
            self.in_style = False

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_title:
            self.title.append(data)
        self.out.append(self.mirror.css(data, self.base_row, self.discover) if self.in_style else data)

    def handle_entityref(self, name):
        self.handle_data('&' + name + ';')

    def handle_charref(self, name):
        self.handle_data('&#' + name + ';')

    def handle_decl(self, decl):
        self.out.append('<!' + decl + '>')


UI_CSS = '''.archive-banner{display:block!important;position:relative!important;z-index:9999!important;margin:0!important;padding:12px 18px!important;background:#eef1f7!important;color:#172131!important;font:14px/1.5 system-ui,sans-serif!important;text-align:left!important;border-bottom:1px solid #bdc8d8!important}.archive-banner a{color:#174c96!important;text-decoration:underline!important}body.archive-index{margin:0;background:#111825;color:#edf2f8;font:16px/1.6 system-ui,sans-serif}main.archive-home{max-width:1080px;margin:0 auto;padding:48px 24px} .archive-home h1{font-size:42px;line-height:1.1;margin:12px 0 24px}.archive-home p{max-width:760px;color:#becbdd}.archive-home a{color:#9ac6ff;overflow-wrap:anywhere}.archive-home input,.archive-home select{font:inherit;padding:12px;border:1px solid #65758b;border-radius:6px;background:#1e2a3d;color:#fff;box-sizing:border-box}.archive-home input{width:min(100%,600px)}.archive-home ul{list-style:none;padding:0}.archive-home li{padding:16px 0;border-bottom:1px solid #344154}.archive-home small{display:block;color:#a8b6c9;overflow-wrap:anywhere}.archive-home nav{margin:28px 0;line-height:2}.archive-home .controls{display:flex;flex-wrap:wrap;gap:12px}.archive-home .eyebrow{letter-spacing:.15em;font-size:12px;text-transform:uppercase;color:#9ac6ff}#pixopoint_menu1 li:hover>ul,#pixopoint_menu1 li:focus-within>ul{display:block!important;visibility:visible!important}'''
UI_CSS += '\n@media (max-height:160px){.archive-banner{display:none!important}}'
UI_JS = ''''use strict';
const list=document.getElementById('pages'), search=document.getElementById('search'), filter=document.getElementById('filter'), status=document.getElementById('results');
fetch('/catalog.json').then(r=>{if(!r.ok)throw Error('Catalog unavailable');return r.json()}).then(pages=>{function draw(){const q=search.value.toLowerCase(); const found=pages.filter(p=>(filter.value==='all'||(filter.value==='forums')===p.forum)&&(p.title+' '+p.url).toLowerCase().includes(q));list.replaceChildren();for(const p of found){const li=document.createElement('li'),a=document.createElement('a'),small=document.createElement('small');a.href=p.path;a.textContent=p.title;small.textContent=(p.forum?'Forum · ':'Site · ')+p.capture.slice(0,4)+'-'+p.capture.slice(4,6)+'-'+p.capture.slice(6,8)+' · '+p.url;li.append(a,small);list.append(li)}status.textContent=found.length+' pages';}search.addEventListener('input',draw);filter.addEventListener('change',draw);document.getElementById('browse-forums').addEventListener('click',()=>{search.value='';filter.value='forums';draw();});draw();}).catch(e=>status.textContent=e.message);
const original=document.getElementById('original-url');if(original){try{original.textContent=decodeURIComponent(location.hash.slice(1));}catch{original.textContent='Invalid source URL';}}
'''
INDEX = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Ace of Angels · Private archive</title><link rel="stylesheet" href="/archive-ui.css"><body class="archive-index"><main class="archive-home"><div class="eyebrow">Flying Rock Enterprises · Personal archive</div><h1>Ace of Angels</h1><p>The surviving official website and forums, recovered from the Internet Archive. Browse the original pages, lore, and conversations. Capture dates vary; this collection combines surviving snapshots rather than recreating one complete day.</p><p>COUNTS. Original scripts and submissions are disabled. Missing pages and images are marked unavailable; game installers are excluded.</p><nav aria-label="Archive starting points">FEATURED</nav><div class="controls"><label>Search pages<br><input id="search" type="search" placeholder="Nation, ship, topic, or page title…"></label><label>Collection<br><select id="filter"><option value="all">All pages</option><option value="site">Website and lore</option><option value="forums">Forum pages</option></select></label></div><p id="results" aria-live="polite">Loading archive index…</p><ul id="pages"></ul><noscript>Enable JavaScript to search the local archive index.</noscript></main><script src="/archive-ui.js"></script></body></html>'''
UNAVAILABLE = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Capture unavailable · Ace of Angels</title><link rel="stylesheet" href="/archive-ui.css"><body class="archive-index"><main class="archive-home"><a href="/">← Archive index</a><h1>Capture unavailable</h1><p>This link could not be recovered, is still awaiting recovery, or points to an external service or excluded download. Its original content has not been recreated.</p><p id="original-url"></p></main><script src="/missing.js"></script></body></html>'''


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--recover', action='store_true')
    ap.add_argument('--limit', type=int, default=2000)
    ap.add_argument('--retry-missing', action='store_true')
    ap.add_argument('--import-indexes', action='store_true')
    ap.add_argument('--import-forum-versions', action='store_true')
    ap.add_argument('--pause', type=float, default=4.0, help='Minimum seconds between sequential archive requests')
    args = ap.parse_args()
    mirror = Mirror(pause=max(1.0, args.pause))
    mirror.seed()
    if args.import_indexes:
        mirror.import_indexes()
    if args.import_forum_versions:
        mirror.import_forum_versions()
    if args.retry_missing:
        for row in mirror.rows.values():
            if row['state'] == 'missing':
                row['state'] = 'pending'
    if args.recover:
        mirror.recover(args.limit)
    mirror.build()


if __name__ == '__main__':
    main()
