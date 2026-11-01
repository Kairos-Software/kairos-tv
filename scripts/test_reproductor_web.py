"""Offline browser regression tests using the app intro as a real video fixture."""
import json
import os
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
TOKEN = 'offline-player-test'

class PlayerScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        executable = os.environ.get('KAIROS_TEST_BROWSER')
        default = Path(r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe')
        if not executable and default.is_file():
            executable = str(default)
        cls.browser = cls.playwright.chromium.launch(
            **({'executable_path': executable} if executable else {}),
            headless=True, args=['--autoplay-policy=no-user-gesture-required'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.events = []
        self.context = self.browser.new_context(viewport={'width': 960, 'height': 540})
        self.context.expose_binding('notifyPlayer', lambda source, msg: self.events.append(json.loads(msg)))
        script = (ROOT / 'app_movil/assets/reproductor_web.js').read_text(encoding='utf-8')
        script = script.replace('__KAIROS_TOKEN__', json.dumps(TOKEN)).replace('__KAIROS_MUTED__', 'true')
        self.context.add_init_script('window.KairosWebPlayer={postMessage:m=>window.notifyPlayer(m)};\n' + script)
        self.context.route('**/*', self.respond)
        self.page = self.context.new_page()

    def tearDown(self):
        self.context.close()

    def respond(self, route):
        request = urlsplit(route.request.url)
        if request.hostname not in ('outer.test', 'player.test'):
            route.abort()
        elif request.path == '/clip.mp4':
            route.fulfill(path=ROOT / 'app_movil/assets/bienvenida/intro_celular.mp4', content_type='video/mp4')
        elif request.path == '/player':
            route.fulfill(content_type='text/html', body="""<html><body>
                <a id="advert" href="/other">Navigation outside player</a>
                <video src="/clip.mp4" muted playsinline controls></video>
                <footer>Website footer</footer></body></html>""")
        elif request.path == '/missing':
            route.fulfill(content_type='text/html', body='<html><body><h1>No video here</h1></body></html>')
        elif request.path == '/denied':
            route.fulfill(status=403, content_type='text/html', body='<html><body>403 Forbidden<hr>nginx</body></html>')
        else:
            child = '/denied' if request.path == '/outer-denied' else '/player'
            route.fulfill(content_type='text/html', body=f"""<html><body>
                <header id="menu"><a href="/other">Menu</a></header>
                <iframe id="embedIframe" src="https://player.test{child}" allowfullscreen></iframe>
                <footer id="footer">Website footer</footer></body></html>""")

    def wait_event(self, event):
        for _ in range(50):
            if any(e.get('event') == event for e in self.events):
                return
            self.page.wait_for_timeout(200)
        self.fail(f'Event {event} not received; got {self.events}')

    def test_real_video_in_cross_origin_frame_fills_screen_without_site_navigation(self):
        self.page.goto('https://outer.test/outer')
        self.wait_event('playing')
        self.assertEqual(self.page.locator('#menu').evaluate('(e)=>getComputedStyle(e).display'), 'none')
        self.assertEqual(self.page.locator('#footer').evaluate('(e)=>getComputedStyle(e).display'), 'none')
        rect = self.page.locator('#embedIframe').bounding_box()
        self.assertEqual((rect['x'], rect['y'], rect['width'], rect['height']), (0, 0, 960, 540))
        self.page.locator('#menu a').evaluate('(e)=>e.click()')
        self.assertEqual(self.page.url, 'https://outer.test/outer')
        self.assertTrue(self.page.evaluate('window.open("https://ads.test") === null'))
        child = self.page.frames[1]
        child.locator('#advert').evaluate('(e)=>e.click()')
        self.assertEqual(child.url, 'https://player.test/player')
        self.assertTrue(child.locator('video').evaluate('(v)=>v.videoWidth>0 && !v.paused'))

    def test_page_load_without_video_never_reports_ready_or_playing(self):
        self.page.goto('https://outer.test/missing')
        self.page.wait_for_timeout(350)
        self.assertEqual(self.events, [])

    def test_forbidden_child_is_diagnosed_without_success(self):
        self.page.goto('https://outer.test/outer-denied')
        self.wait_event('forbidden')
        self.assertFalse(any(e['event'] in ('ready', 'playing') for e in self.events))

    def test_mute_command_reaches_cross_origin_player(self):
        self.page.goto('https://outer.test/outer')
        self.wait_event('playing')
        self.page.evaluate('(c)=>window.postMessage(c,"*")',
            {'kairosWebPlayer': TOKEN, 'muted': False, 'play': False})
        child = self.page.frames[1]
        child.wait_for_function('document.querySelector("video").muted === false')

if __name__ == '__main__':
    unittest.main()
