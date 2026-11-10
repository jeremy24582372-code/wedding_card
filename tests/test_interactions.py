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


def run_profile(browser, engine, name, settings, base):
    mobile = name != 'desktop'
    ios = name in ('iphone', 'ipad-desktop-ua')
    context = browser.new_context(**settings, accept_downloads=True)
    if name == 'ipad-desktop-ua':
        context.add_init_script("Object.defineProperty(navigator, 'platform', {get: () => 'MacIntel'}); Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 5});")
    context.route('**/cdn-cgi/**', lambda route: route.fulfill(status=204, body=''))
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    calendar_url = base + 'assets/Jeremy_Yuri_Wedding.ics?v=20261013-timed'
    try:
        ready(page, base + '#invitation')
        page.screenshot(path=str(OUTPUT / f'{engine}-{name}-invitation.png'), full_page=True)
        assert page.locator('#calendar-dialog').count() == 0, 'Old calendar choice dialog must be gone'
        assert page.locator('#google-calendar').count() == 0, 'Google Calendar option must be gone'
        calendar = page.locator('#add-calendar')
        assert calendar.is_visible()
        assert calendar.evaluate('(a) => a.tagName') == 'A', 'The visible button must be a native link'
        assert calendar.get_attribute('aria-haspopup') is None
        assert calendar.get_attribute('href') is not None
        assert calendar.evaluate('(a) => a.textContent.length > 0')

        # Verify the navigation uses a separate tab in ALL browser profiles.
        # Intercept Google Maps to avoid relying on live Google responses.
        map_link = page.locator('#open-map')
        map_url = map_link.get_attribute('href')
        parsed = urlsplit(map_url)
        assert parsed.netloc == 'www.google.com' and parsed.path == '/maps/dir/'
        assert parse_qs(parsed.query) == {'api': ['1'], 'destination': [DESTINATION]}
        assert map_link.get_attribute('target') == '_blank'
        assert 'noopener' in (map_link.get_attribute('rel') or '')
        assert 'noreferrer' in (map_link.get_attribute('rel') or '')
        context.route('https://www.google.com/maps/**',
                      lambda route: route.fulfill(status=200, content_type='text/html',
                                                  body='<title>Google Maps test destination</title>'))
        original_url = page.url
        with context.expect_page(timeout=15000) as new_page:
            activate(page, '#open-map', mobile)
        popup = new_page.value
        popup.wait_for_url('**/maps/dir/**', timeout=15000)
        assert popup.url == map_url, f'Navigation destination changed: {popup.url}'
        assert len(context.pages) == 2
        assert page.url == original_url, 'Invitation should remain in original tab'
        assert page.locator('#invitation').is_visible()
        popup.close()
        assert page.url == original_url

        if ios:
            assert calendar.get_attribute('href') == calendar_url
            assert calendar.get_attribute('download') is None
            assert calendar.get_attribute('type') == 'text/calendar'
            assert calendar.get_attribute('target') == '_self'
            # A real trusted tap must request the original ICS immediately,
            # without opening a choice dialog or a Google Calendar page.
            with page.expect_request('**/assets/Jeremy_Yuri_Wedding.ics?*') as pending:
                activate(page, '#add-calendar', mobile)
            assert pending.value.url == calendar_url
            assert len(context.pages) == 1
            mode = 'single-tap native ICS request'
        else:
            # Preloading reuses byte-identical ICS in a Blob on desktop/Android.
            page.wait_for_function("document.querySelector('#add-calendar').href.startsWith('blob:')", timeout=15000)
            assert calendar.get_attribute('download') == 'Jeremy_Yuri_Wedding.ics'
            blob_url = calendar.get_attribute('href')
            with page.expect_download() as pending:
                activate(page, '#add-calendar', mobile)
            download = pending.value
            assert download.suggested_filename == 'Jeremy_Yuri_Wedding.ics'
            assert Path(download.path()).read_bytes() == ICS
            assert calendar.get_attribute('href') == blob_url
            assert page.url == base + '#invitation'
            assert len(context.pages) == 1
            mode = 'single-click byte-identical ICS download'
        assert not errors, errors
        REPORT.append({'test': f'{engine}/{name}', 'status': 'passed', 'calendar': mode, 'map': 'opens a separate tab; original invitation preserved'})
    except Exception:
        try:
            page.screenshot(path=str(OUTPUT / f'{engine}-{name}-failure.png'), full_page=True)
        except Exception:
            pass
        raise
    finally:
        context.close()


def run_fetch_failure(browser, engine, base):
    # When background prefetch fails, the visible link still points at a real
    # .ics file. Focusing it can retry without opening a choice dialog.
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
        page.wait_for_timeout(200)
        assert len(requests) == 1, requests
        calendar = page.locator('#add-calendar')
        assert calendar.evaluate('(a) => a.href').startswith(base)
        assert page.locator('#calendar-dialog').count() == 0
        calendar.focus()
        page.wait_for_function("document.querySelector('#add-calendar').href.startsWith('blob:')", timeout=15000)
        assert len(requests) == 2, requests
        with page.expect_download() as pending:
            calendar.click()
        assert Path(pending.value.path()).read_bytes() == ICS
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
    print(f'PASS: {len(REPORT)} test groups. Native iOS Calendar import still requires device verification.')


if __name__ == '__main__':
    main()
