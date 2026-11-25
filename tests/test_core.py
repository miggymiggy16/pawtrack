"""Core regression tests for PawTrack.

Run with:  python -m unittest discover -s tests -v
These tests use the real MySQL database via the storage layer, so run them
from the project folder with the app's .env present.
"""
import base64
import pathlib
import unittest

from app import app
from pawtrack.config import FACE_MATCH_THRESHOLD, ID_TYPES
from pawtrack.services.ocr import parse_fields, run_ocr, scan_id
from pawtrack.services.id_face import detect_face_on_id, match_faces
from pawtrack.storage import load

SAMPLE_ID = pathlib.Path(__file__).resolve().parents[1] / 'static/uploads/verification/id_bc2332c077144a2a9716e4db1b51479a.png'
AUTH = 'Basic ' + base64.b64encode(b'pawtrack:pawtracktestonly').decode()


class TestConfig(unittest.TestCase):
    def test_shared_constants(self):
        self.assertEqual(len(ID_TYPES), 4)
        self.assertIn('Philippine National ID', ID_TYPES)
        self.assertGreater(FACE_MATCH_THRESHOLD, 0)


class TestIdentityPrimitives(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = SAMPLE_ID.read_bytes()

    def test_ocr_extracts_all_required_fields(self):
        text, _ = run_ocr(self.img)
        f = parse_fields(text)
        for key in ('full_name', 'date_of_birth', 'id_number', 'address'):
            self.assertTrue(f.get(key), f'{key} was not extracted')

    def test_scan_id_complete(self):
        result = scan_id(self.img, 'Philippine National ID')
        self.assertTrue(result['complete'], result.get('missing'))

    def test_face_detection_and_self_match(self):
        desc, _crop = detect_face_on_id(self.img)
        self.assertTrue(desc)
        matched, score = match_faces(desc, desc)
        self.assertTrue(matched)
        self.assertGreaterEqual(score, FACE_MATCH_THRESHOLD)


class TestPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        cls.user = load('users')[0]

    def setUp(self):
        self.client = app.test_client()
        with self.client.session_transaction() as s:
            s['user_id'] = self.user['user_id']

    def test_main_pages_render(self):
        for path in ['/admin/dashboard', '/animals', '/animals/new', '/settings',
                     '/vaccinations', '/inventory', '/reports', '/analytics',
                     '/sales', '/notifications', '/users']:
            with self.subTest(path=path):
                r = self.client.get(path, headers={'Authorization': AUTH})
                self.assertEqual(r.status_code, 200, f'{path} -> {r.status_code}')

    def test_all_analytics_reports_render(self):
        keys = ['species', 'ownership', 'sex', 'breed', 'status', 'monitoring',
                'trends', 'vaccines', 'coverage-species', 'coverage-ownership',
                'inventory-value', 'inventory-alerts', 'vaccine-stock']
        for key in keys:
            with self.subTest(key=key):
                r = self.client.get(f'/analytics/report/{key}', headers={'Authorization': AUTH})
                self.assertEqual(r.status_code, 200, f'{key} -> {r.status_code}')


if __name__ == '__main__':
    unittest.main(verbosity=2)
