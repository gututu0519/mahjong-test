"""验证浏览器已关闭后才能复用同一份资料。"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lobby_profiles import LobbyProfiles


class LobbyProfilesTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        with patch('lobby_profiles.tempfile.gettempdir', return_value=str(self.root)):
            self.pool = LobbyProfiles()
        self.addCleanup(self.pool.close)

    def test_same_preset_reuses_only_after_release(self):
        first = self.pool.acquire(' alice ', 'test-pass')
        self.assertFalse(first.returning)
        self.assertEqual(self.root, first.path.parent)
        self.assertNotIn('alice', first.path.name)
        (first.path / 'test-marker').touch()
        self.pool.release(first, reusable=True)
        second = self.pool.acquire('alice', 'test-pass')
        self.assertTrue(second.returning)
        self.assertEqual(first.path, second.path)
        self.assertTrue((second.path / 'test-marker').is_file())
        self.pool.release(first)
        self.assertTrue(second.path.is_dir())
        self.pool.release(second)
        self.assertFalse(second.path.exists())

    def test_concurrent_profiles_are_exclusive_and_close_respects_active_leases(self):
        with ThreadPoolExecutor(max_workers=5) as executor:
            leases = list(executor.map(lambda _: self.pool.acquire('same', 'test'), range(5)))
        self.assertEqual(5, len({lease.path for lease in leases}))
        self.assertFalse(any(lease.returning for lease in leases))
        self.pool.release(leases[0], reusable=True)
        self.pool.close()
        self.assertFalse(leases[0].path.exists())
        for lease in leases[1:]:
            self.assertTrue(lease.path.is_dir())
            self.pool.release(lease, reusable=True)
            self.assertFalse(lease.path.exists())
        with self.assertRaises(RuntimeError):
            self.pool.acquire('same', 'test')

    def test_password_change_and_account_boundaries(self):
        first = self.pool.acquire('alice', 'test1')
        self.pool.release(first, reusable=True)
        for account, password in [('alice', 'test2'), ('alicet', 'est1'), ('other', 'test1')]:
            with self.subTest(account=account):
                second = self.pool.acquire(account, password)
                self.assertFalse(second.returning)
                self.assertNotEqual(first.path, second.path)
                self.pool.release(second)

    def test_idle_limit_and_expiry(self):
        with patch.object(self.pool, 'MAX_IDLE', 1):
            first = self.pool.acquire('alice', 'test')
            second = self.pool.acquire('bob', 'test')
            self.pool.release(first, reusable=True)
            self.pool.release(second, reusable=True)
            self.assertFalse(first.path.exists())
        with patch.object(self.pool, 'IDLE_SECONDS', 0):
            fresh = self.pool.acquire('bob', 'test')
        self.assertFalse(second.path.exists())
        self.assertFalse(fresh.returning)
        self.pool.release(fresh)

    def test_replaced_directory_is_not_used_or_deleted(self):
        first = self.pool.acquire('alice', 'test')
        self.pool.release(first, reusable=True)
        detached = self.root / 'detached-test-profile'
        self.assertEqual(self.root, first.path.resolve().parent)
        first.path.rename(detached)
        first.path.mkdir()
        (first.path / 'other-owner').touch()
        second = self.pool.acquire('alice', 'test')
        self.assertFalse(second.returning)
        self.pool.release(second)
        self.pool.close()
        self.assertTrue((first.path / 'other-owner').is_file())

    def test_delayed_file_unlock_retried(self):
        first = self.pool.acquire('alice', 'test')
        with patch('lobby_profiles.shutil.rmtree', side_effect=PermissionError):
            self.pool.release(first)
        self.assertTrue(first.path.is_dir())
        second = self.pool.acquire('alice', 'test')
        self.assertFalse(first.path.exists())
        self.assertFalse(second.returning)
        self.pool.release(second)


if __name__ == '__main__':
    unittest.main()
