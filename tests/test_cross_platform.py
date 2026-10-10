import os
import sys
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.notifier import notifier
from backend.repo_manager import RepoManager
from backend.app import _open_file_manager, _open_code_editor, _open_terminal

class TestCrossPlatformSupport(unittest.TestCase):

    def test_cross_platform_notifier(self):
        """Tests that notifier calls appropriate notification method per platform"""
        with patch.object(notifier, "_send_windows_toast") as mock_win, \
             patch.object(notifier, "_send_macos_notification") as mock_mac, \
             patch.object(notifier, "_send_linux_notification") as mock_linux:

            # Test Windows
            with patch("sys.platform", "win32"):
                notifier._send_desktop_notification("Title", "Message")
                mock_win.assert_called_once_with("Title", "Message")

            # Test macOS
            with patch("sys.platform", "darwin"):
                notifier._send_desktop_notification("Title", "Message")
                mock_mac.assert_called_once_with("Title", "Message")

            # Test Linux
            with patch("sys.platform", "linux"):
                notifier._send_desktop_notification("Title", "Message")
                mock_linux.assert_called_once_with("Title", "Message")

    def test_repo_manager_frozen_hook_generation(self):
        """Tests that hook scripts generate frozen binary commands when running from packaged exe"""
        temp_dir = tempfile.mkdtemp(prefix="sentinel_hook_test_")
        try:
            rm = RepoManager()

            # Test frozen mode
            with patch("sys.frozen", True, create=True), \
                 patch("sys.executable", "D:/GitSentinel/GitSentinel.exe"):
                rm.install_local_hook(temp_dir)
                hook_path = os.path.join(temp_dir, ".git", "hooks", "pre-commit")
                with open(hook_path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.assertIn("GitSentinel.exe", content)
                self.assertIn("intercept --repo-dir", content)

            # Test source mode
            with patch("sys.frozen", False, create=True):
                rm.install_local_hook(temp_dir)
                with open(hook_path, "r", encoding="utf-8") as f:
                    content_src = f.read()
                self.assertIn("interceptor_gui.py", content_src)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_cross_platform_open_handlers(self):
        """Tests file manager, editor and terminal opening per platform"""
        with patch("subprocess.Popen") as mock_popen:
            # File Manager on Windows
            with patch("sys.platform", "win32"):
                _open_file_manager("C:/Users/test")
                mock_popen.assert_called()

            # File Manager on macOS
            with patch("sys.platform", "darwin"):
                _open_file_manager("/Users/test")
                mock_popen.assert_called_with(["open", os.path.normpath("/Users/test")])

            # File Manager on Linux
            with patch("sys.platform", "linux"):
                _open_file_manager("/home/test")
                mock_popen.assert_called_with(["xdg-open", os.path.normpath("/home/test")])

    def test_terminal_openers(self):
        """Tests terminal opening commands across platforms"""
        with patch("subprocess.Popen") as mock_popen, \
             patch("shutil.which", return_value="/usr/bin/gnome-terminal"):
            with patch("sys.platform", "linux"):
                _open_terminal("/home/test")
                mock_popen.assert_called()

            with patch("sys.platform", "darwin"):
                _open_terminal("/Users/test")
                mock_popen.assert_called_with(["open", "-a", "Terminal", os.path.normpath("/Users/test")])

if __name__ == "__main__":
    unittest.main()
