#!/usr/bin/env python3
"""Privacy-first multi-machine synchronization through GitHub Contents API.

The GitHub repository stores only encrypted, compressed ContextGO snapshots.
The password-derived key never leaves the machine.  Each device writes its own
shard, so independent machines do not overwrite one another's state.
"""

from __future__ import annotations

import base64
import contextlib
import getpass
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from context_config import config_dir
    from context_runtime import atomic_write_json, atomic_write_text, ensure_private_dir, restrict_file
except ImportError:  # pragma: no cover
    from .context_config import config_dir
    from .context_runtime import atomic_write_json, atomic_write_text, ensure_private_dir, restrict_file

try:
    from memory_index import export_observations_payload, import_observations_payload
except ImportError:  # pragma: no cover
    from .memory_index import export_observations_payload, import_observations_payload

__all__ = [
    "SyncError",
    "SyncConfig",
    "GitHubContentsClient",
    "init_sync",
    "sync_status",
    "pull_sync",
    "push_sync",
    "run_sync",
    "sync_config_exists",
    "auto_sync_enabled",
    "disable_sync",
]

SYNC_SCHEMA_VERSION = 1
SYNC_FORMAT = "contextgo-sync-v1"
SYNC_ROOT = "contextgo/v1/devices"
MANIFEST_PATH = "contextgo/v1/manifest.json"
CONFIG_NAME = "sync.json"
KEY_NAME = "sync.key"
DEFAULT_BRANCH = "main"
DEFAULT_API = "https://api.github.com"


class SyncError(RuntimeError):
    """Raised for invalid sync configuration, crypto, or remote failures."""


@dataclass
class SyncConfig:
    repository: str
    branch: str
    device_id: str
    salt: bytes
    key_check: bytes
    api_url: str = DEFAULT_API
    store_key: bool = True
    max_records_per_shard: int = 500
    auto_sync: bool = True

    @property
    def config_path(self) -> Path:
        return config_dir() / CONFIG_NAME

    @property
    def key_path(self) -> Path:
        return config_dir() / KEY_NAME

    @property
    def device_prefix(self) -> str:
        return f"{SYNC_ROOT}/{self.device_id}-"

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": SYNC_SCHEMA_VERSION,
            "format": SYNC_FORMAT,
            "repository": self.repository,
            "branch": self.branch,
            "device_id": self.device_id,
            "salt_b64": _b64(self.salt),
            "key_check_b64": _b64(self.key_check),
            "api_url": self.api_url,
            "store_key": self.store_key,
            "max_records_per_shard": self.max_records_per_shard,
            "auto_sync": self.auto_sync,
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> SyncConfig:
        if raw.get("format") != SYNC_FORMAT or int(raw.get("schema_version", 0)) != SYNC_SCHEMA_VERSION:
            raise SyncError("不支持的同步配置版本")
        repository = _normalize_repository(str(raw.get("repository", "")))
        device_id = str(raw.get("device_id", "")).strip()
        if not device_id or any(
            ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in device_id
        ):
            raise SyncError("同步设备 ID 无效")
        try:
            salt = _unb64(str(raw["salt_b64"]))
            key_check = _unb64(str(raw["key_check_b64"]))
        except (KeyError, ValueError) as exc:
            raise SyncError("同步配置中的密钥参数损坏") from exc
        return cls(
            repository=repository,
            branch=str(raw.get("branch") or DEFAULT_BRANCH),
            device_id=device_id,
            salt=salt,
            key_check=key_check,
            api_url=str(raw.get("api_url") or DEFAULT_API).rstrip("/"),
            store_key=bool(raw.get("store_key", True)),
            max_records_per_shard=max(1, min(int(raw.get("max_records_per_shard", 500)), 5000)),
            auto_sync=bool(raw.get("auto_sync", True)),
        )


def _config_path() -> Path:
    return config_dir() / CONFIG_NAME


def _load_config() -> SyncConfig:
    path = _config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SyncError("尚未配置同步，请先运行 contextgo sync init") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise SyncError(f"读取同步配置失败：{path}") from exc
    if not isinstance(raw, dict):
        raise SyncError("同步配置必须是 JSON 对象")
    return SyncConfig.from_json(raw)


def sync_config_exists() -> bool:
    return _config_path().is_file()


def auto_sync_enabled() -> bool:
    """Return whether a configured sync profile permits unattended sync."""
    if not sync_config_exists():
        return False
    try:
        return _load_config().auto_sync
    except SyncError:
        return False


def disable_sync() -> dict[str, Any]:
    """Disable automatic sync while preserving the profile and encrypted data."""
    cfg = _load_config()
    cfg.auto_sync = False
    atomic_write_json(cfg.config_path, cfg.to_json())
    return {"disabled": True, "repository": cfg.repository, "device_id": cfg.device_id}


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def _normalize_repository(repository: str) -> str:
    value = repository.strip()
    if value.startswith("https://github.com/"):
        value = value.removeprefix("https://github.com/")
    if value.startswith("http://github.com/"):
        value = value.removeprefix("http://github.com/")
    value = value.removesuffix(".git").strip("/")
    parts = value.split("/")
    if len(parts) != 2 or not all(parts) or any(part in {".", ".."} for part in parts):
        raise SyncError("仓库必须是 owner/repository 或 GitHub 仓库 URL")
    if any(not all(ch.isalnum() or ch in "-_." for ch in part) for part in parts):
        raise SyncError("GitHub 仓库名称包含无效字符")
    return value


def _password_from_args(password: str | None = None, *, prompt: bool = True) -> str:
    if password:
        return password
    for name in ("CONTEXTGO_SYNC_PASSWORD", "CONTEXTGO_SYNC_PASSPHRASE"):
        value = os.environ.get(name, "")
        if value:
            return value
    if not prompt:
        raise SyncError("未提供同步口令；请设置 CONTEXTGO_SYNC_PASSWORD")
    first = getpass.getpass("ContextGO 同步口令（不会上传到 GitHub）：")
    if not first:
        raise SyncError("同步口令不能为空")
    return first


def _derive_key(password: str, salt: bytes) -> bytes:
    try:
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    except ImportError as exc:
        raise SyncError('同步功能需要加密依赖，请安装：pipx install "contextgo[sync]"') from exc
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password.encode("utf-8"))


def _key_check(key: bytes) -> bytes:
    return hashlib.sha256(b"ContextGO sync key check v1\0" + key).digest()


def _load_key(cfg: SyncConfig, *, password: str | None = None, prompt: bool = True) -> bytes:
    if cfg.store_key and cfg.key_path.is_file():
        try:
            key = _unb64(cfg.key_path.read_text(encoding="ascii").strip())
        except (OSError, ValueError) as exc:
            raise SyncError("本机同步密钥文件损坏") from exc
        if _key_check(key) != cfg.key_check:
            raise SyncError("本机同步密钥校验失败，请重新初始化同步")
        return key
    key = _derive_key(_password_from_args(password, prompt=prompt), cfg.salt)
    if not secrets.compare_digest(_key_check(key), cfg.key_check):
        raise SyncError("同步口令不正确")
    return key


def _save_key(cfg: SyncConfig, key: bytes) -> None:
    ensure_private_dir(cfg.key_path.parent)
    atomic_write_text(cfg.key_path, _b64(key) + "\n")
    restrict_file(cfg.key_path)


def init_sync(
    repository: str,
    *,
    branch: str = DEFAULT_BRANCH,
    password: str | None = None,
    store_key: bool = True,
    device_id: str | None = None,
    api_url: str = DEFAULT_API,
    max_records_per_shard: int = 500,
    auto_sync: bool = True,
) -> SyncConfig:
    """Create a local sync configuration; no network request is made."""
    repo = _normalize_repository(repository)
    secret = _password_from_args(password)
    salt = secrets.token_bytes(16)
    # A manifest contains only public KDF parameters.  When the repository is
    # already initialized, reusing its salt lets another machine derive the
    # same key from the same passphrase without copying a private config file.
    provisional = SyncConfig(
        repository=repo,
        branch=branch.strip() or DEFAULT_BRANCH,
        device_id=device_id or uuid.uuid4().hex[:16],
        salt=salt,
        key_check=b"0" * 32,
        api_url=api_url.rstrip("/"),
        store_key=store_key,
        auto_sync=auto_sync,
    )
    token = _github_token()
    if token:
        try:
            remote_manifest = GitHubContentsClient(provisional, token).get_file(MANIFEST_PATH)
            if remote_manifest:
                raw_manifest = _decode_github_file(remote_manifest)
                parsed_manifest = json.loads(raw_manifest.decode("utf-8"))
                if isinstance(parsed_manifest, dict) and parsed_manifest.get("format") == SYNC_FORMAT:
                    salt = _unb64(str(parsed_manifest["salt_b64"]))
        except (SyncError, KeyError, ValueError, json.JSONDecodeError):
            # A malformed/old manifest is treated as an uninitialized remote;
            # push will replace it only after the user explicitly runs sync.
            pass
    key = _derive_key(secret, salt)
    cfg = SyncConfig(
        repository=repo,
        branch=branch.strip() or DEFAULT_BRANCH,
        device_id=device_id or uuid.uuid4().hex[:16],
        salt=salt,
        key_check=_key_check(key),
        api_url=api_url.rstrip("/"),
        store_key=store_key,
        max_records_per_shard=max(1, min(int(max_records_per_shard), 5000)),
        auto_sync=auto_sync,
    )
    ensure_private_dir(config_dir())
    atomic_write_json(cfg.config_path, cfg.to_json())
    if store_key:
        _save_key(cfg, key)
    else:
        with contextlib.suppress(FileNotFoundError):
            cfg.key_path.unlink()
    return cfg


class GitHubContentsClient:
    """Small standard-library GitHub Contents API client."""

    def __init__(self, cfg: SyncConfig, token: str | None = None, *, timeout: int = 30) -> None:
        self.cfg = cfg
        self.token = token or _github_token()
        if not self.token:
            raise SyncError("未找到 GitHub Token，请设置 CONTEXTGO_GITHUB_TOKEN 或 GITHUB_TOKEN")
        self.timeout = max(5, timeout)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in path.split("/"))
        url = f"{self.cfg.api_url}/repos/{self.cfg.repository}/contents/{encoded_path}"
        if method == "GET":
            url += "?ref=" + urllib.parse.quote(self.cfg.branch, safe="")
        data = None
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ContextGO-sync/0.13",
        }
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read(400).decode("utf-8", errors="replace")
            if exc.code == 404:
                return None
            if exc.code == 409:
                raise SyncError("GitHub 同步发生版本冲突，请重试") from exc
            raise SyncError(f"GitHub API HTTP {exc.code}: {detail[:240]}") from exc
        except (OSError, urllib.error.URLError) as exc:
            raise SyncError(f"GitHub API 网络错误：{exc}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise SyncError("GitHub API 返回了无法解析的响应") from exc

    def list_files(self) -> list[dict[str, Any]]:
        data = self._request("GET", SYNC_ROOT)
        if data is None:
            return []
        if not isinstance(data, list):
            raise SyncError("同步目录不是 GitHub 文件列表")
        return [item for item in data if isinstance(item, dict) and str(item.get("name", "")).endswith(".cgo")]

    def get_file(self, path: str) -> dict[str, Any] | None:
        data = self._request("GET", path)
        return data if isinstance(data, dict) else None

    def put_file(self, path: str, content: bytes, *, sha: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "message": f"ContextGO sync: update {Path(path).name}",
            "content": base64.b64encode(content).decode("ascii"),
            "branch": self.cfg.branch,
        }
        if sha:
            payload["sha"] = sha
        result = self._request("PUT", path, payload)
        if not isinstance(result, dict):
            raise SyncError("GitHub 写入返回了无效响应")
        return result

    def delete_file(self, path: str, sha: str) -> None:
        self._request(
            "DELETE",
            path,
            {"message": f"ContextGO sync: remove {Path(path).name}", "sha": sha, "branch": self.cfg.branch},
        )


def _github_token() -> str:
    for name in ("CONTEXTGO_GITHUB_TOKEN", "GITHUB_TOKEN"):
        token = os.environ.get(name, "").strip()
        if token:
            return token
    gh = shutil.which("gh")
    if gh:
        try:
            proc = subprocess.run([gh, "auth", "token"], capture_output=True, text=True, timeout=10, check=False)
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    return ""


def _encrypt_payload(payload: dict[str, Any], key: bytes, *, path: str) -> bytes:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise SyncError('同步功能需要加密依赖，请安装：pipx install "contextgo[sync]"') from exc
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    compressed = zlib.compress(raw, level=9)
    nonce = secrets.token_bytes(12)
    aad = f"{SYNC_FORMAT}:{path}".encode()
    ciphertext = AESGCM(key).encrypt(nonce, compressed, aad)
    envelope = {
        "format": SYNC_FORMAT,
        "compression": "zlib",
        "nonce_b64": _b64(nonce),
        "ciphertext_b64": _b64(ciphertext),
    }
    return json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _decrypt_payload(raw: bytes, key: bytes, *, path: str) -> dict[str, Any]:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise SyncError('同步功能需要加密依赖，请安装：pipx install "contextgo[sync]"') from exc
    try:
        envelope = json.loads(raw.decode("utf-8"))
        if envelope.get("format") != SYNC_FORMAT:
            raise ValueError("format")
        nonce = _unb64(str(envelope["nonce_b64"]))
        ciphertext = _unb64(str(envelope["ciphertext_b64"]))
        aad = f"{SYNC_FORMAT}:{path}".encode()
        compressed = AESGCM(key).decrypt(nonce, ciphertext, aad)
        payload = json.loads(zlib.decompress(compressed).decode("utf-8"))
    except Exception as exc:
        raise SyncError(f"无法解密同步分片：{path}；口令错误或文件已损坏") from exc
    if not isinstance(payload, dict) or payload.get("format") != SYNC_FORMAT:
        raise SyncError(f"同步分片载荷无效：{path}")
    return payload


def _portable_payload(limit: int) -> dict[str, Any]:
    payload = export_observations_payload("", limit=limit, source_type="all", portable=True)
    payload["format"] = SYNC_FORMAT
    payload["schema_version"] = SYNC_SCHEMA_VERSION
    payload["device_context"] = {"storage": "local", "paths": "redacted"}
    return payload


def _decode_github_file(item: dict[str, Any]) -> bytes:
    encoded = item.get("content")
    if not encoded:
        raise SyncError(f"GitHub 文件缺少内容：{item.get('path', '')}")
    return base64.b64decode(str(encoded).replace("\n", ""))


def _chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[pos : pos + size] for pos in range(0, len(items), size)] or [[]]


def sync_status(*, include_remote: bool = False) -> dict[str, Any]:
    cfg = _load_config()
    payload: dict[str, Any] = {
        "configured": True,
        "repository": cfg.repository,
        "branch": cfg.branch,
        "device_id": cfg.device_id,
        "key_stored_locally": cfg.store_key and cfg.key_path.is_file(),
        "auto_sync": cfg.auto_sync,
        "config_path": cfg.config_path.name,
        "privacy": "encrypted-only; paths-redacted",
    }
    if include_remote:
        client = GitHubContentsClient(cfg)
        files = client.list_files()
        payload["remote_shards"] = len(files)
        payload["remote_names"] = [str(item.get("name", "")) for item in files]
    return payload


def pull_sync(*, password: str | None = None, token: str | None = None) -> dict[str, Any]:
    cfg = _load_config()
    key = _load_key(cfg, password=password, prompt=False)
    client = GitHubContentsClient(cfg, token)
    imported = skipped = 0
    files = client.list_files()
    for item in files:
        path = str(item.get("path", ""))
        if not path.startswith(cfg.device_prefix):
            remote = client.get_file(path)
            if remote is None:
                continue
            raw = _decode_github_file(remote)
            payload = _decrypt_payload(raw, key, path=path)
            result = import_observations_payload(payload, sync_from_storage=False)
            imported += int(result.get("inserted", 0))
            skipped += int(result.get("skipped", 0))
    return {"pulled_shards": len(files), "inserted": imported, "skipped": skipped, "repository": cfg.repository}


def push_sync(*, password: str | None = None, token: str | None = None, limit: int = 50_000) -> dict[str, Any]:
    cfg = _load_config()
    key = _load_key(cfg, password=password, prompt=False)
    client = GitHubContentsClient(cfg, token)
    manifest = {
        "format": SYNC_FORMAT,
        "schema_version": SYNC_SCHEMA_VERSION,
        "salt_b64": _b64(cfg.salt),
        "kdf": "scrypt-n32768-r8-p1",
        "encryption": "AES-256-GCM",
        "path_policy": "encrypted-only; paths-redacted",
    }
    manifest_item = client.get_file(MANIFEST_PATH)
    if manifest_item:
        try:
            remote_manifest = json.loads(_decode_github_file(manifest_item).decode("utf-8"))
            remote_salt = _unb64(str(remote_manifest["salt_b64"]))
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            raise SyncError("远端同步清单损坏，拒绝覆盖") from exc
        if remote_manifest.get("format") != SYNC_FORMAT or remote_salt != cfg.salt:
            raise SyncError("远端同步清单与本机密钥参数不一致；请重新执行 sync init 读取现有清单")
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    client.put_file(MANIFEST_PATH, manifest_bytes, sha=str(manifest_item["sha"]) if manifest_item else None)

    payload = _portable_payload(max(1, min(int(limit), 50_000)))
    observations = list(payload.get("observations") or [])
    chunks = _chunks(observations, cfg.max_records_per_shard)
    existing = {str(item.get("path")): item for item in client.list_files()}
    uploaded = 0
    for index, observations_chunk in enumerate(chunks, 1):
        path = f"{cfg.device_prefix}{index:06d}.cgo"
        chunk_payload = dict(payload)
        chunk_payload["observations"] = observations_chunk
        chunk_payload["total_observations"] = len(observations_chunk)
        chunk_payload["chunk_index"] = index
        chunk_payload["chunk_count"] = len(chunks)
        encrypted = _encrypt_payload(chunk_payload, key, path=path)
        client.put_file(path, encrypted, sha=str(existing[path]["sha"]) if path in existing else None)
        uploaded += 1
    removed = 0
    for path, item in existing.items():
        if path.startswith(cfg.device_prefix) and not any(
            path == f"{cfg.device_prefix}{i:06d}.cgo" for i in range(1, len(chunks) + 1)
        ):
            sha = str(item.get("sha", ""))
            if sha:
                client.delete_file(path, sha)
                removed += 1
    return {
        "uploaded_shards": uploaded,
        "removed_shards": removed,
        "observations": len(observations),
        "repository": cfg.repository,
    }


def run_sync(*, password: str | None = None, token: str | None = None, limit: int = 50_000) -> dict[str, Any]:
    """Pull remote memories then push the merged local snapshot."""
    pulled = pull_sync(password=password, token=token)
    pushed = push_sync(password=password, token=token, limit=limit)
    return {"pulled": pulled, "pushed": pushed, "completed_at": datetime.now(timezone.utc).isoformat()}
