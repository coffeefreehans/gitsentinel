import os
import sys
import unittest
import tempfile
import shutil
import subprocess
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import ConfigManager, config_manager
from backend.security_scanner import SecurityScanner
from backend.key_manager import KeyManager
from backend.repo_manager import RepoManager
from backend.notifier import notifier

class TestGitSentinel(unittest.TestCase):

    def test_01_security_scanner(self):
        print("\n[TEST 1] Testing Security Scanner...")
        scanner = SecurityScanner()

        # Test sensitive filenames
        staged_files = ["src/main.py", ".env", "config/id_rsa", "docs/README.md"]
        file_findings = scanner.scan_files(staged_files)
        self.assertTrue(len(file_findings) >= 2)
        found_names = [f["file"] for f in file_findings]
        self.assertIn(".env", found_names)
        self.assertIn("config/id_rsa", found_names)
        print("  -> Sensitive file rule detection: PASSED")

        # Test secret leak patterns in diff
        sample_diff = """
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,3 +1,6 @@
+OPENAI_KEY = "sk-proj-abcdef1234567890abcdef1234567890"
+AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
+normal_var = "hello world"
"""
        diff_findings = scanner.scan_diff(sample_diff)
        self.assertTrue(len(diff_findings) >= 2)
        titles = [d["title"] for d in diff_findings]
        self.assertTrue(any("OpenAI" in t for t in titles))
        self.assertTrue(any("AWS" in t for t in titles))
        print("  -> Secret leak pattern regex scanner: PASSED")

        # Full scan
        full = scanner.run_full_scan(staged_files, sample_diff)
        self.assertEqual(full["status"], "critical")
        self.assertGreaterEqual(full["total_issues"], 4)
        print("  -> Full scan status aggregation: PASSED")

    def test_02_key_manager(self):
        print("\n[TEST 2] Testing Key Manager...")
        km = KeyManager()
        keys = km.list_keys()
        print(f"  -> Discovered {len(keys)} existing SSH keys in {km.ssh_dir}")
        for k in keys:
            print(f"     - {k['name']}: {k['type']} | Fingerprint: {k['fingerprint'][:30]}...")

        user_cfg = km.get_git_user_config()
        print(f"  -> Global Git User: {user_cfg.get('global_user_name')} <{user_cfg.get('global_user_email')}>")

    def test_03_repo_lifecycle_and_hook_intercept(self):
        print("\n[TEST 3] Testing Git Repo Lifecycle & Pre-commit Interception...")
        temp_dir = tempfile.mkdtemp(prefix="sentinel_test_")
        try:
            # 1. Init git repo
            subprocess.run(["git", "init"], cwd=temp_dir, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "SentinelTester"], cwd=temp_dir, check=True)
            subprocess.run(["git", "config", "user.email", "tester@sentinel.local"], cwd=temp_dir, check=True)

            rm = RepoManager()
            status = rm.get_repo_status(temp_dir)
            self.assertIsNotNone(status)
            self.assertEqual(status["name"], os.path.basename(temp_dir))
            print(f"  -> Initialized and analyzed test repo: {status['name']}")

            # 2. Install Sentinel pre-commit, pre-push and post-commit hooks
            rm.install_local_hook(temp_dir)
            hook_file = os.path.join(temp_dir, ".git", "hooks", "pre-commit")
            push_hook_file = os.path.join(temp_dir, ".git", "hooks", "pre-push")
            self.assertTrue(os.path.exists(hook_file))
            self.assertTrue(os.path.exists(push_hook_file))
            with open(hook_file, "r", encoding="utf-8") as f:
                self.assertIn("GitSentinel", f.read())
            with open(push_hook_file, "r", encoding="utf-8") as f:
                self.assertIn("GitSentinel", f.read())
            print("  -> Sentinel pre-commit & pre-push hook installation: PASSED")

            # 3. Test interceptor logic directly in non-interactive/bypass and simulated modes
            # Staged file 1: normal file
            sample_file = os.path.join(temp_dir, "app.py")
            with open(sample_file, "w") as f:
                f.write("print('hello world')\n")
            subprocess.run(["git", "add", "app.py"], cwd=temp_dir, check=True)

            # Test bypass flag GIT_SENTINEL_SKIP=1
            env = os.environ.copy()
            env["GIT_SENTINEL_SKIP"] = "1"
            res = subprocess.run(
                ["git", "commit", "-m", "bypass commit"],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env
            )
            self.assertEqual(res.returncode, 0)
            print("  -> Pre-commit bypass mode (GIT_SENTINEL_SKIP=1): PASSED")

            # Staged file 2: sensitive file (.env)
            env_file = os.path.join(temp_dir, ".env")
            with open(env_file, "w") as f:
                f.write("SECRET_KEY=1234567890\n")
            subprocess.run(["git", "add", ".env"], cwd=temp_dir, check=True)

            # Test interceptor aborting commit (simulated via headless auto abort)
            env_abort = os.environ.copy()
            env_abort["GIT_SENTINEL_HEADLESS"] = "1"
            env_abort["GIT_SENTINEL_AUTO_ABORT"] = "1"
            res_abort = subprocess.run(
                ["git", "commit", "-m", "bad commit with env"],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env_abort
            )
            self.assertNotEqual(res_abort.returncode, 0)
            output_str = (res_abort.stdout or "") + (res_abort.stderr or "")
            self.assertTrue("aborted" in output_str.lower() or "拦截" in output_str)
            print("  -> Commit interception abortion (blocked as expected): PASSED")

            # Test interceptor approving commit (simulated via headless auto approve)
            env_approve = os.environ.copy()
            env_approve["GIT_SENTINEL_HEADLESS"] = "1"
            env_approve["GIT_SENTINEL_AUTO_APPROVE"] = "1"
            res_approve = subprocess.run(
                ["git", "commit", "-m", "good commit"],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env_approve
            )
            self.assertEqual(res_approve.returncode, 0)
            print("  -> Commit interception approval (proceeds as expected): PASSED")

            # 4. Test git push intercept against a local bare remote
            remote_bare = tempfile.mkdtemp(prefix="sentinel_bare_")
            try:
                subprocess.run(["git", "init", "--bare"], cwd=remote_bare, check=True, capture_output=True)
                subprocess.run(["git", "remote", "add", "origin", remote_bare], cwd=temp_dir, check=True, capture_output=True)
                
                # Test pre-push abort (blocked by GitSentinel)
                res_push_abort = subprocess.run(
                    ["git", "push", "-u", "origin", "HEAD"],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=env_abort
                )
                self.assertNotEqual(res_push_abort.returncode, 0)
                push_abort_output = (res_push_abort.stdout or "") + (res_push_abort.stderr or "")
                self.assertTrue("aborted" in push_abort_output.lower() or "拦截" in push_abort_output or "failed to push" in push_abort_output.lower())
                print("  -> Push interception abortion (blocked as expected): PASSED")

                # Test pre-push approve (allowed by GitSentinel)
                res_push_approve = subprocess.run(
                    ["git", "push", "-u", "origin", "HEAD"],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=env_approve
                )
                self.assertEqual(res_push_approve.returncode, 0)
                print("  -> Push interception approval (uploaded as expected): PASSED")
            finally:
                shutil.rmtree(remote_bare, ignore_errors=True)

            # 5. Uninstall hooks
            rm.uninstall_local_hook(temp_dir)
            self.assertFalse(os.path.exists(hook_file))
            self.assertFalse(os.path.exists(push_hook_file))
            print("  -> Sentinel hook uninstallation: PASSED")

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_04_notifier(self):
        print("\n[TEST 4] Testing Windows Toast & Event Notifier...")
        notified = []
        notifier.add_listener(lambda n: notified.append(n))
        notifier.notify("GitSentinel 测试通知", "系统测试执行正常", event_type="info")
        self.assertEqual(len(notified), 1)
        self.assertEqual(notified[0]["title"], "GitSentinel 测试通知")
        print("  -> Notifier event dispatch & Windows toast dispatch: PASSED")

    def test_05_identity_aggregation(self):
        print("\n[TEST 5] Testing Git Identity Aggregation & Global Hooks...")
        km = KeyManager()
        rm = RepoManager()
        repos = rm.scan_directories()
        self.assertTrue(len(repos) >= 1)
        
        identities_result = km.get_all_git_identities(repos)
        self.assertIn("identities", identities_result)
        self.assertGreaterEqual(identities_result["total_identities"], 1)
        print(f"  -> Discovered {identities_result['total_identities']} active Git identities across {len(repos)} repos")

        # Test global hook toggle
        orig_status = rm.is_global_hooks_enabled()
        res_on = rm.set_global_hooks(True)
        self.assertTrue(res_on)
        self.assertTrue(rm.is_global_hooks_enabled())
        print("  -> Global core.hooksPath activation: PASSED")

        if not orig_status:
            rm.set_global_hooks(False)
            self.assertFalse(rm.is_global_hooks_enabled())
            print("  -> Global core.hooksPath deactivation: PASSED")
        else:
            print("  -> Preserved user's global hooks enabled status: PASSED")

if __name__ == "__main__":
    unittest.main()
