"""Browser regression tests. External links are intercepted; no events are saved.

Run: python -m pip install playwright==1.56.0
     python -m playwright install --with-deps chromium webkit
     python tests/test_interactions.py

Playwright's mobile emulation is NOT a real iOS app-handoff test.
"""
from __future__ import annotations

import functools
import json
import re
import tempfile
import threading
import traceback
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'test-results'
OUTPUT.mkdir(exist_ok=True)
ICS = (ROOT / 'assets/Jeremy_Yuri_Wedding.ics').read_bytes()
DESTINATION = '晶宴日光香頌 臺北市中山區民生東路三段8號'
EVENT = {
    'action': ['TEMPLATE'],
    'text': ['謝僑育 & 佐藤友里 婚宴'],
    'dates': ['20270123T033000Z/20270123T080000Z'],
    'details': ['誠摯邀請您一同見證我們的幸福時刻。\n11:30 賓客入場\n12:00 午宴開席\n16:00 婚宴結束\n晶宴日光香頌（B2圓環廳）'],
    'location': ['晶宴日光香頌（B2圓環廳），臺北市中山區民生東路三段8號'],
    'ctz': ['Asia/Taipei'],
}
IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1'
IPAD = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15'
ANDROID = 'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36'
PROFILES = {
    'desktop': {'viewport': {'width': 1280, 'height': 900}},
    'iphone': {'viewport': {'width': 390, 'height': 844}, 'user_agent': IPHONE, 'is_mobile': True, 'has_touch': True},
    'ipad-desktop-ua': {'viewport': {'width': 820, 'height': 1180}, 'user_agent': IPAD, 'is_mobile': True, 'has_touch': True},
    'android': {'viewport': {'width': 412, 'height': 915}, 'user_agent': ANDROID, 'is_mobile': True, 'has_touch': True},
}
REPORT = []


class QuietHandler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.ics': 'text/calendar; charset=utf-8'}

    def log_message(self, *args):
        pass


def check_calendar():
    assert ICS.endswith(b'\r\n')
    assert b'\n' not in ICS.replace(b'\r\n', b''), 'ICS must retain CRLF line endings'
    for line in ICS.split(b'\r\n'):
        assert len(line) <= 75, 'RFC 5545 folded lines must not exceed 75 octets'
        line.decode('utf-8')
    text = re.sub(r'\r\n[ \t]', '', ICS.decode('utf-8'))
    expected = [
        'UID:jeremy-yuri-wedding-20270123@jeremy-yuri-wedding-invitation.jeremy-hsieh.chatgpt.site',
        'DTSTART:20270123T033000Z', 'DTEND:20270123T080000Z',
        'SUMMARY:謝僑育 & 佐藤友里 婚宴',
        'LOCATION:晶宴日光香頌（B2圓環廳）\\, 臺北市中山區民生東路三段8號',
        'TRIGGER;RELATED=START:-P1D',
    ]
    for line in expected:
        assert line in text, line
    for stamp, expected_time in [('20270123T033000+0000', '2027-01-23 11:30'), ('20270123T080000+0000', '2027-01-23 16:00')]:
        actual = datetime.strptime(stamp, '%Y%m%dT%H%M%S%z').astimezone(ZoneInfo('Asia/Taipei'))
        assert actual.strftime('%Y-%m-%d %H:%M') == expected_time
    REPORT.append({'test': 'reference-calendar-data', 'status': 'passed'})


def ready(page, url):
    page.goto(url, wait_until='load')
    page.locator('#site-loading').wait_for(state='hidden')
    assert page.locator('#invitation').is_visible()
    assert page.locator('#site-content').get_attribute('inert') is None


def activate(page, selector, mobile):
    if mobile:
        page.locator(selector).tap()
    else:
        page.locator(selector).click()


def closed(page):
    # Link handlers deliberately close on the next task, after native activation.
    # A download event can arrive first; assert the eventual UI state, not timing.
    page.wait_for_function("!document.querySelector('#calendar-dialog').open", timeout=5000)
    assert not page.locator('#calendar-dialog').evaluate('(d) => d.open')


def run_profile(browser, engine, name, settings, base):
    mobile = name != 'desktop'
    ios = name in ('iphone', 'ipad-desktop-ua')
    context = browser.new_context(**settings, accept_downloads=True)
    if name == 'ipad-desktop-ua':
        context.add_init_script("Object.defineProperty(navigator, 'platform', {get: () => 'MacIntel'}); Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 5});")
    # The imported reference HTML contains an origin-specific Cloudflare script.
    # It is not part of the invitation and does not exist on GitHub Pages.
    context.route('**/cdn-cgi/**', lambda route: route.fulfill(status=204, body=''))
    external = []
    dialogs = []
    errors = []
    activations = []

    def capture_external(route):
        external.append(route.request.url)
        route.fulfill(content_type='text/html', body='<title>Captured external link</title><p>No event was created.</p>')

    context.route('https://www.google.com/maps/**', capture_external)
    context.route('https://calendar.google.com/**', capture_external)
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('dialog', lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))
    page.on('console', lambda message: activations.append(json.loads(message.text[11:])) if message.text.startswith('ACTIVATION:') else None)
    url = base + '#invitation'
    try:
        ready(page, url)
        page.screenshot(path=str(OUTPUT / f'{engine}-{name}-invitation.png'), full_page=True)
        map_url = page.locator('#open-map').get_attribute('href')
        parsed = urlsplit(map_url)
        assert parsed.netloc == 'www.google.com' and parsed.path == '/maps/dir/'
        assert parse_qs(parsed.query) == {'api': ['1'], 'destination': [DESTINATION]}
        assert page.locator('#open-map').get_attribute('target') == ('_self' if mobile else '_blank')
        activate(page, '#open-map', mobile)
        page.wait_for_timeout(200)
        assert external[-1] == map_url
        if mobile:
            assert len(context.pages) == 1 and page.url == map_url
            page.go_back(wait_until='load')
            page.locator('#site-loading').wait_for(state='hidden')
            assert page.locator('#invitation').is_visible()
        else:
            assert len(context.pages) == 2
            context.pages[-1].close()
        assert not dialogs, 'Do not replace the native Maps prompt with a fake JavaScript confirm'

        activate(page, '#add-calendar', mobile)
        assert page.locator('#calendar-dialog').evaluate('(d) => d.open')
        page.screenshot(path=str(OUTPUT / f'{engine}-{name}-calendar.png'), full_page=True)
        activate(page, '#close-dialog', mobile)
        closed(page)
        activate(page, '#add-calendar', mobile)
        google_url = page.locator('#google-calendar').get_attribute('href')
        assert parse_qs(urlsplit(google_url).query) == EVENT
        assert page.locator('#google-calendar').get_attribute('target') == ('_self' if mobile else '_blank')
        page.evaluate("""() => document.querySelector('#google-calendar').addEventListener('click', e => {
            console.log('ACTIVATION:' + JSON.stringify({trusted: e.isTrusted, dialogOpen: document.querySelector('#calendar-dialog').open}));
        })""")
        activate(page, '#google-calendar', mobile)
        page.wait_for_timeout(200)
        assert external[-1] == google_url
        assert activations[-1] == {'trusted': True, 'dialogOpen': True}
        if mobile:
            assert len(context.pages) == 1 and page.url == google_url
            page.go_back(wait_until='load')
            page.locator('#site-loading').wait_for(state='hidden')
        else:
            assert len(context.pages) == 2
            context.pages[-1].close()
        closed(page)

        activate(page, '#add-calendar', mobile)
        phone = page.locator('#download-ics')
        if ios:
            href = phone.get_attribute('href')
            assert href == base + 'assets/Jeremy_Yuri_Wedding.ics?v=20261013-timed'
            assert phone.get_attribute('download') is None
            assert phone.get_attribute('type') == 'text/calendar'
            assert phone.get_attribute('target') == '_self'
            # Linux WebKit cannot display iOS Calendar's native import sheet.
            # Assert an actual tap requests the real .ics, not a blob/data URL.
            with page.expect_request('**/assets/Jeremy_Yuri_Wedding.ics?*'):
                activate(page, '#download-ics', mobile)
            assert len(context.pages) == 1
        else:
            page.wait_for_function("document.querySelector('#download-ics').href.startsWith('blob:')")
            blob_url = phone.get_attribute('href')
            with page.expect_download() as pending:
                activate(page, '#download-ics', mobile)
            download = pending.value
            assert download.suggested_filename == 'Jeremy_Yuri_Wedding.ics'
            assert Path(download.path()).read_bytes() == ICS
            closed(page)
            activate(page, '#add-calendar', mobile)
            assert phone.get_attribute('href') == blob_url, 'Reuse the prepared calendar instead of fetching repeatedly'
        assert not errors, errors
        REPORT.append({'test': f'{engine}/{name}', 'status': 'passed', 'map': map_url, 'google': google_url, 'phone_calendar': 'real .ics navigation' if ios else 'byte-identical .ics download'})
    except Exception:
        try:
            page.screenshot(path=str(OUTPUT / f'{engine}-{name}-failure.png'), full_page=True)
        except Exception:
            pass
        raise
    finally:
        context.close()


def run_fetch_failure(browser, engine, base):
    context = browser.new_context(accept_downloads=True)
    requests = []
    def response(route):
        requests.append(route.request.url)
        if len(requests) == 1:
            route.fulfill(status=503, body='Temporarily unavailable')
        else:
            route.fulfill(status=200, content_type='text/calendar', body=ICS)
    context.route('**/cdn-cgi/**', lambda route: route.fulfill(status=204, body=''))
    context.route('**/assets/Jeremy_Yuri_Wedding.ics?*', response)
    page = context.new_page()
    try:
        ready(page, base + '#invitation')
        page.wait_for_timeout(100)
        assert len(requests) == 1
        assert page.locator('#download-ics').evaluate('(a) => a.href').startswith(base)
        page.locator('#add-calendar').click()
        page.wait_for_function("document.querySelector('#download-ics').href.startsWith('blob:')")
        assert len(requests) == 2
        with page.expect_download() as pending:
            page.locator('#download-ics').click()
        assert Path(pending.value.path()).read_bytes() == ICS
        closed(page)
        REPORT.append({'test': f'{engine}/calendar-fetch-retry', 'status': 'passed'})
    finally:
        context.close()


def record_failure(name):
    error = traceback.format_exc()
    print(error, flush=True)
    REPORT.append({'test': name, 'status': 'failed', 'error': error})


def main():
    check_calendar()
    with tempfile.TemporaryDirectory() as temporary:
        (Path(temporary) / 'wedding_card').symlink_to(ROOT, target_is_directory=True)
        server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=temporary))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}/wedding_card/'
        try:
            with sync_playwright() as pw:
                for engine in ('chromium', 'webkit'):
                    browser = getattr(pw, engine).launch()
                    try:
                        for name, settings in PROFILES.items():
                            try:
                                run_profile(browser, engine, name, settings, base)
                            except Exception:
                                record_failure(f'{engine}/{name}')
                        try:
                            run_fetch_failure(browser, engine, base)
                        except Exception:
                            record_failure(f'{engine}/calendar-fetch-retry')
                    finally:
                        browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
            (OUTPUT / 'report.json').write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(REPORT, ensure_ascii=False, indent=2))
    failures = [item for item in REPORT if item['status'] == 'failed']
    if failures:
        raise SystemExit(f'FAIL: {len(failures)} of {len(REPORT)} test groups failed.')
    print(f'PASS: {len(REPORT)} test groups. Real iOS Calendar / Google Maps app confirmation still requires device verification.')


if __name__ == '__main__':
    main()
