from __future__ import annotations

import base64
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from contextgo import context_sync as sync


class SyncCryptoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key = sync._derive_key("correct horse battery staple", b"0123456789abcdef")
        self.path = "contextgo/v1/devices/device-a-000001.cgo"

    def test_ciphertext_round_trip_and_plaintext_absent(self) -> None:
        payload = {
            "format": sync.SYNC_FORMAT,
            "observations": [{"content": "private marker C:/Users/alice/project"}],
        }
        encrypted = sync._encrypt_payload(payload, self.key, path=self.path)
        self.assertNotIn(b"private marker", encrypted)
        self.assertNotIn(b"C:/Users/alice", encrypted)
        self.assertEqual(sync._decrypt_payload(encrypted, self.key, path=self.path), payload)

    def test_portable_text_redacts_windows_and_posix_home_paths(self) -> None:
        from contextgo import memory_index

        text = "see C:\\Users\\alice\\secret\\file.txt and /home/bob/private/key plus /Users/carol/project"
        cleaned = memory_index._portable_text(text)
        self.assertNotIn("alice", cleaned)
        self.assertNotIn("/home/bob", cleaned)
        self.assertNotIn("/Users/carol", cleaned)
        self.assertIn("<local-path-redacted>", cleaned)

    def test_wrong_key_and_wrong_path_are_rejected(self) -> None:
        payload = {"format": sync.SYNC_FORMAT, "observations": []}
        encrypted = sync._encrypt_payload(payload, self.key, path=self.path)
        wrong_key = sync._derive_key("different password", b"0123456789abcdef")
        with self.assertRaises(sync.SyncError):
            sync._decrypt_payload(encrypted, wrong_key, path=self.path)
        with self.assertRaises(sync.SyncError):
            sync._decrypt_payload(encrypted, self.key, path="contextgo/v1/devices/other.cgo")

    def test_repository_validation(self) -> None:
        self.assertEqual(sync._normalize_repository("https://github.com/dunova/ContextGO.git"), "dunova/ContextGO")
        for bad in ("", "owner", "a/b/c", "../repo", "owner/repo space"):
            with self.assertRaises(sync.SyncError):
                sync._normalize_repository(bad)


class SyncConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config_dir = Path(self.tmp.name) / "config"
        self.env = mock.patch.dict("os.environ", {"CONTEXTGO_CONFIG_DIR": str(self.config_dir)}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_init_status_disable_without_network(self) -> None:
        with mock.patch.object(sync, "_github_token", return_value=""):
            cfg = sync.init_sync("dunova/context-sync", password="strong passphrase", device_id="machine-a")
        self.assertTrue(cfg.config_path.is_file())
        self.assertTrue(cfg.key_path.is_file())
        raw = cfg.config_path.read_text(encoding="utf-8")
        self.assertNotIn("strong passphrase", raw)
        status = sync.sync_status()
        self.assertTrue(status["configured"])
        self.assertTrue(status["auto_sync"])
        self.assertTrue(sync.disable_sync()["disabled"])
        self.assertFalse(sync.auto_sync_enabled())

    def test_remote_manifest_reuses_salt_for_second_machine(self) -> None:
        salt = b"shared-salt-1234"
        manifest = {
            "format": sync.SYNC_FORMAT,
            "schema_version": 1,
            "salt_b64": sync._b64(salt),
        }
        remote = {"content": base64.b64encode(json.dumps(manifest).encode()).decode()}
        client = mock.MagicMock()
        client.get_file.return_value = remote
        with (
            mock.patch.object(sync, "_github_token", return_value="token"),
            mock.patch.object(sync, "GitHubContentsClient", return_value=client),
        ):
            cfg = sync.init_sync("dunova/context-sync", password="same password", device_id="machine-b")
        self.assertEqual(cfg.salt, salt)

    def test_config_parse_rejects_bad_shape_and_bad_device(self) -> None:
        bad = {"format": sync.SYNC_FORMAT, "schema_version": 1, "repository": "dunova/repo", "device_id": "bad/device"}
        with self.assertRaises(sync.SyncError):
            sync.SyncConfig.from_json(bad)
        with self.assertRaises(sync.SyncError):
            sync.SyncConfig.from_json({"format": "old", "schema_version": 0})
        with self.assertRaises(sync.SyncError):
            sync.SyncConfig.from_json(
                {
                    "format": sync.SYNC_FORMAT,
                    "schema_version": 1,
                    "repository": "owner/repo",
                    "device_id": "dev",
                    "salt_b64": sync._b64(b"salt"),
                }
            )

    def test_repository_urls_and_config_file_errors(self) -> None:
        self.assertEqual(sync._normalize_repository("http://github.com/a/b.git"), "a/b")
        with self.assertRaises(sync.SyncError):
            sync._normalize_repository("owner/repo space")
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with mock.patch.object(sync.Path, "read_text", side_effect=OSError("unreadable")):
            with self.assertRaises(sync.SyncError):
                sync._load_config()

    def test_uninitialized_config_and_empty_interactive_password(self) -> None:
        with self.assertRaises(sync.SyncError):
            sync._load_config()
        with (
            mock.patch.dict(
                "os.environ", {"CONTEXTGO_SYNC_PASSWORD": "", "CONTEXTGO_SYNC_PASSPHRASE": ""}, clear=False
            ),
            mock.patch.object(sync.getpass, "getpass", return_value=""),
        ):
            with self.assertRaises(sync.SyncError):
                sync._password_from_args(prompt=True)

    def test_auto_sync_false_when_missing_or_corrupt_config(self) -> None:
        self.assertFalse(sync.auto_sync_enabled())
        self.config_dir.mkdir(parents=True, exist_ok=True)
        (self.config_dir / sync.CONFIG_NAME).write_text("not-json", encoding="utf-8")
        self.assertFalse(sync.auto_sync_enabled())

    def test_password_sources_and_missing_password(self) -> None:
        with mock.patch.dict("os.environ", {"CONTEXTGO_SYNC_PASSWORD": "from-env"}, clear=False):
            self.assertEqual(sync._password_from_args(prompt=False), "from-env")
        with mock.patch.dict(
            "os.environ", {"CONTEXTGO_SYNC_PASSWORD": "", "CONTEXTGO_SYNC_PASSPHRASE": "from-passphrase"}, clear=False
        ):
            self.assertEqual(sync._password_from_args(prompt=False), "from-passphrase")
        with mock.patch.dict(
            "os.environ", {"CONTEXTGO_SYNC_PASSWORD": "", "CONTEXTGO_SYNC_PASSPHRASE": ""}, clear=False
        ):
            with self.assertRaises(sync.SyncError):
                sync._password_from_args(prompt=False)

    def test_disable_requires_existing_config(self) -> None:
        with mock.patch.object(sync, "_load_config", side_effect=sync.SyncError("missing")):
            with self.assertRaises(sync.SyncError):
                sync.disable_sync()

    def test_github_token_resolution_is_local_only(self) -> None:
        with mock.patch.dict("os.environ", {"CONTEXTGO_GITHUB_TOKEN": "env-token"}, clear=False):
            self.assertEqual(sync._github_token(), "env-token")
        with mock.patch.dict("os.environ", {"CONTEXTGO_GITHUB_TOKEN": "", "GITHUB_TOKEN": "github-token"}, clear=False):
            self.assertEqual(sync._github_token(), "github-token")
        proc = mock.Mock(returncode=0, stdout="cli-token\n")
        with (
            mock.patch.dict("os.environ", {"CONTEXTGO_GITHUB_TOKEN": "", "GITHUB_TOKEN": ""}, clear=False),
            mock.patch.object(sync.shutil, "which", return_value="gh"),
            mock.patch.object(sync.subprocess, "run", return_value=proc),
        ):
            self.assertEqual(sync._github_token(), "cli-token")
        with (
            mock.patch.dict("os.environ", {"CONTEXTGO_GITHUB_TOKEN": "", "GITHUB_TOKEN": ""}, clear=False),
            mock.patch.object(sync.shutil, "which", return_value="gh"),
            mock.patch.object(sync.subprocess, "run", side_effect=sync.subprocess.TimeoutExpired("gh", 10)),
        ):
            self.assertEqual(sync._github_token(), "")


class SyncTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config_dir = Path(self.tmp.name) / "config"
        self.env = mock.patch.dict("os.environ", {"CONTEXTGO_CONFIG_DIR": str(self.config_dir)}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        with mock.patch.object(sync, "_github_token", return_value=""):
            self.cfg = sync.init_sync(
                "dunova/context-sync",
                password="transport password",
                device_id="machine-a",
                max_records_per_shard=2,
            )

    def test_push_writes_public_manifest_and_encrypted_device_shards(self) -> None:
        client = mock.MagicMock()
        client.get_file.return_value = None
        client.list_files.return_value = []
        exported = {
            "schema_version": 1,
            "portable": True,
            "observations": [{"content": "one"}, {"content": "two"}, {"content": "three"}],
        }
        with (
            mock.patch.object(sync, "GitHubContentsClient", return_value=client),
            mock.patch.object(sync, "export_observations_payload", return_value=exported),
        ):
            result = sync.push_sync(token="token")
        self.assertEqual(result["uploaded_shards"], 2)
        calls = client.put_file.call_args_list
        self.assertEqual(calls[0].args[0], sync.MANIFEST_PATH)
        manifest = json.loads(calls[0].args[1])
        self.assertEqual(manifest["encryption"], "AES-256-GCM")
        for call in calls[1:]:
            self.assertTrue(call.args[0].startswith(self.cfg.device_prefix))
            self.assertNotIn(b"one", call.args[1])

    def test_push_rejects_mismatched_remote_manifest(self) -> None:
        remote_manifest = {
            "format": sync.SYNC_FORMAT,
            "schema_version": 1,
            "salt_b64": sync._b64(b"different-salt!!"),
        }
        client = mock.MagicMock()
        client.get_file.return_value = {
            "sha": "manifest-sha",
            "content": base64.b64encode(json.dumps(remote_manifest).encode()).decode(),
        }
        with (
            mock.patch.object(sync, "GitHubContentsClient", return_value=client),
            mock.patch.object(sync, "export_observations_payload") as exporter,
        ):
            with self.assertRaises(sync.SyncError):
                sync.push_sync(token="token")
        exporter.assert_not_called()
        client.put_file.assert_not_called()

    def test_pull_fetches_file_contents_and_skips_own_shards(self) -> None:
        key = sync._load_key(self.cfg, prompt=False)
        other_path = "contextgo/v1/devices/machine-b-000001.cgo"
        payload = {"format": sync.SYNC_FORMAT, "observations": [{"content": "shared"}]}
        encrypted = sync._encrypt_payload(payload, key, path=other_path)
        listing = [
            {"path": other_path, "name": "machine-b-000001.cgo"},
            {"path": f"{self.cfg.device_prefix}000001.cgo", "name": "machine-a-000001.cgo"},
        ]
        client = mock.MagicMock()
        client.list_files.return_value = listing
        client.get_file.return_value = {"content": base64.b64encode(encrypted).decode()}
        with (
            mock.patch.object(sync, "GitHubContentsClient", return_value=client),
            mock.patch.object(
                sync, "import_observations_payload", return_value={"inserted": 1, "skipped": 0}
            ) as importer,
        ):
            result = sync.pull_sync(token="token")
        self.assertEqual(result["inserted"], 1)
        client.get_file.assert_called_once_with(other_path)
        importer.assert_called_once()

    def test_status_include_remote_lists_names(self) -> None:
        client = mock.MagicMock()
        client.list_files.return_value = [{"name": "a.cgo"}, {"name": "b.cgo"}]
        with mock.patch.object(sync, "GitHubContentsClient", return_value=client):
            status = sync.sync_status(include_remote=True)
        self.assertEqual(status["remote_shards"], 2)
        self.assertEqual(status["remote_names"], ["a.cgo", "b.cgo"])

    def test_run_sync_combines_pull_and_push(self) -> None:
        with (
            mock.patch.object(sync, "pull_sync", return_value={"inserted": 1}) as pull,
            mock.patch.object(sync, "push_sync", return_value={"uploaded_shards": 2}) as push,
        ):
            result = sync.run_sync(token="token")
        self.assertEqual(result["pulled"], {"inserted": 1})
        self.assertEqual(result["pushed"], {"uploaded_shards": 2})
        pull.assert_called_once()
        push.assert_called_once()

    def test_load_key_rejects_wrong_password_without_stored_key(self) -> None:
        self.cfg.key_path.unlink()
        self.cfg.store_key = False
        with self.assertRaises(sync.SyncError):
            sync._load_key(self.cfg, password="wrong", prompt=False)

    def test_decode_github_file_requires_content(self) -> None:
        with self.assertRaises(sync.SyncError):
            sync._decode_github_file({"path": "missing.cgo"})


class GitHubClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = sync.SyncConfig(
            repository="owner/repo",
            branch="main",
            device_id="dev",
            salt=b"0123456789abcdef",
            key_check=b"x" * 32,
            api_url="https://api.example.test",
        )

    def test_requires_token(self) -> None:
        with mock.patch.object(sync, "_github_token", return_value=""):
            with self.assertRaises(sync.SyncError):
                sync.GitHubContentsClient(self.cfg)

    def test_list_files_filters_cgo_entries(self) -> None:
        client = sync.GitHubContentsClient(self.cfg, token="token")
        with mock.patch.object(client, "_request", return_value=[{"name": "a.cgo"}, {"name": "notes.txt"}]):
            self.assertEqual(client.list_files(), [{"name": "a.cgo"}])

    def test_list_files_rejects_non_list(self) -> None:
        client = sync.GitHubContentsClient(self.cfg, token="token")
        with mock.patch.object(client, "_request", return_value={"content": []}):
            with self.assertRaises(sync.SyncError):
                client.list_files()

    def test_put_and_delete_file_payloads(self) -> None:
        client = sync.GitHubContentsClient(self.cfg, token="token")
        with mock.patch.object(client, "_request", return_value={"ok": True}) as request:
            self.assertEqual(client.put_file("a/b.cgo", b"payload", sha="abc"), {"ok": True})
            client.delete_file("a/b.cgo", "abc")
        self.assertEqual(request.call_args_list[0].args[0], "PUT")
        self.assertEqual(request.call_args_list[1].args[0], "DELETE")

    def test_put_file_rejects_invalid_response_and_get_file_filters(self) -> None:
        client = sync.GitHubContentsClient(self.cfg, token="token")
        with mock.patch.object(client, "_request", return_value=None):
            with self.assertRaises(sync.SyncError):
                client.put_file("a.cgo", b"data")
        with mock.patch.object(client, "_request", return_value=[{"not": "a file"}]):
            self.assertIsNone(client.get_file("a.cgo"))

    def test_request_404_returns_none_and_bad_json_errors(self) -> None:
        client = sync.GitHubContentsClient(self.cfg, token="token")
        err = urllib.error.HTTPError("url", 404, "not found", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=err):
            self.assertIsNone(client._request("GET", "missing"))
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"not-json"
        with mock.patch("urllib.request.urlopen", return_value=response):
            with self.assertRaises(sync.SyncError):
                client._request("GET", "bad")

    def test_request_409_and_network_error(self) -> None:
        client = sync.GitHubContentsClient(self.cfg, token="token")
        for code in (409, 500):
            err = urllib.error.HTTPError("url", code, "error", {}, None)
            with mock.patch("urllib.request.urlopen", side_effect=err):
                with self.assertRaises(sync.SyncError):
                    client._request("GET", "error")
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            with self.assertRaises(sync.SyncError):
                client._request("GET", "offline")

    def test_decrypt_corrupt_and_invalid_payload(self) -> None:
        key = sync._derive_key("test-password", b"0123456789abcdef")
        path = "contextgo/v1/devices/dev-000001.cgo"
        with self.assertRaises(sync.SyncError):
            sync._decrypt_payload(b"not-json", key, path=path)
        with self.assertRaises(sync.SyncError):
            sync._decrypt_payload(b'{"format":"wrong"}', key, path=path)

    def test_chunks_and_decode_helpers(self) -> None:
        self.assertEqual(sync._chunks([{"x": 1}, {"x": 2}], 1), [[{"x": 1}], [{"x": 2}]])
        self.assertEqual(sync._chunks([], 2), [[]])
        raw = base64.b64encode(b"hello").decode()
        self.assertEqual(sync._decode_github_file({"content": raw}), b"hello")

    def test_load_key_corrupt_file_and_config_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp) / "cfg"
            cfg_dir.mkdir()
            with mock.patch.dict("os.environ", {"CONTEXTGO_CONFIG_DIR": str(cfg_dir)}, clear=False):
                cfg = sync.SyncConfig(
                    repository="owner/repo",
                    branch="main",
                    device_id="dev",
                    salt=b"0123456789abcdef",
                    key_check=b"x" * 32,
                    store_key=True,
                )
                cfg.key_path.write_text("bad!!!", encoding="utf-8")
                with self.assertRaises(sync.SyncError):
                    sync._load_key(cfg, prompt=False)
                cfg.config_path.write_text("[]", encoding="utf-8")
                with self.assertRaises(sync.SyncError):
                    sync._load_config()


if __name__ == "__main__":
    unittest.main()
