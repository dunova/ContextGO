#!/usr/bin/env python3
"""Unit tests for secret_redaction module.

Covers every token type supported by sanitize_text() and the
_SECRET_REPLACEMENTS list.
"""

from __future__ import annotations

import unittest

from contextgo.secret_redaction import _SECRET_REPLACEMENTS, sanitize_text


class TestOpenAIKeys(unittest.TestCase):
    """OpenAI / Anthropic API key redaction."""

    def test_openai_sk_key(self) -> None:
        text = "use sk-abcdefghijklmnopqrstuvwx to call OpenAI"
        result = sanitize_text(text)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwx", result)
        self.assertIn("sk-***", result)

    def test_openai_sk_proj_key(self) -> None:
        text = "key=sk-proj-ABCDEFGHIJKLMNOPQRSTUV1234567890"
        result = sanitize_text(text)
        self.assertNotIn("sk-proj-ABCDEFGHIJKLMNOPQRSTUV1234567890", result)
        self.assertIn("sk-proj-***", result)

    def test_anthropic_sk_ant_key(self) -> None:
        text = "ANTHROPIC_API_KEY=sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVwxyz1234"
        result = sanitize_text(text)
        self.assertNotIn("sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVwxyz1234", result)
        self.assertIn("sk-ant-***", result)


class TestGitHubTokens(unittest.TestCase):
    """GitHub PAT and token redaction."""

    def test_ghp_personal_access_token(self) -> None:
        token = "ghp_" + "A" * 36
        result = sanitize_text(f"token={token}")
        self.assertNotIn(token, result)
        self.assertIn("ghp_***", result)

    def test_ghu_oauth_token(self) -> None:
        token = "ghu_" + "B" * 36
        result = sanitize_text(f"Authorization: Bearer {token}")
        self.assertNotIn(token, result)

    def test_ghs_server_token(self) -> None:
        token = "ghs_" + "C" * 36
        result = sanitize_text(token)
        self.assertNotIn(token, result)
        self.assertIn("ghs_***", result)

    def test_ghr_actions_refresh_token(self) -> None:
        token = "ghr_" + "D" * 36
        result = sanitize_text(f"ghr token: {token}")
        self.assertNotIn(token, result)
        self.assertIn("ghr_***", result)

    def test_github_fine_grained_pat(self) -> None:
        token = "github_pat_" + "E" * 36
        result = sanitize_text(f"export GH_TOKEN={token}")
        self.assertNotIn(token, result)
        self.assertIn("github_pat_***", result)


class TestAWSKeys(unittest.TestCase):
    """AWS access key redaction."""

    def test_akia_access_key(self) -> None:
        key = "AKIAIOSFODNN7EXAMPLE1234"
        result = sanitize_text(f"AWS_ACCESS_KEY_ID={key}")
        self.assertNotIn(key, result)
        self.assertIn("AKIA***", result)

    def test_asia_temporary_key(self) -> None:
        key = "ASIAIOSFODNN7EXAMPLE1234"
        result = sanitize_text(key)
        self.assertNotIn(key, result)
        self.assertIn("AKIA***", result)

    def test_aroa_role_key(self) -> None:
        key = "AROAIOSFODNN7EXAMPLE1234"
        result = sanitize_text(key)
        self.assertNotIn(key, result)
        self.assertIn("AKIA***", result)


class TestSlackTokens(unittest.TestCase):
    """Slack token redaction (xoxb-, xoxp-, etc.)."""

    def test_xoxb_bot_token(self) -> None:
        token = "xoxb-FAKE0FAKE0F-FAKE0FAKE0F-FAKEfakeFAKEfake"
        result = sanitize_text(f"SLACK_TOKEN={token}")
        self.assertNotIn(token, result)
        self.assertIn("xox?-***", result)

    def test_xoxp_user_token(self) -> None:
        token = "xoxp-FAKE0FAKE0F-FAKE0FAKE0F-FAKEfakeFAKEfake"
        result = sanitize_text(token)
        self.assertNotIn(token, result)
        self.assertIn("xox?-***", result)

    def test_xoxa_app_level_token(self) -> None:
        token = "xoxa-2-FAKE0FAKE0F-FAKE0FAKE0F-FAKEfakeFAKEfake"
        result = sanitize_text(token)
        self.assertNotIn(token, result)
        self.assertIn("xox?-***", result)


class TestJWTTokens(unittest.TestCase):
    """JWT token redaction."""

    def test_jwt_three_segment(self) -> None:
        # A realistic JWT-like token: header.payload.signature
        header = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        payload = "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0"
        sig = "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        jwt = f"{header}.{payload}.{sig}"
        result = sanitize_text(f"Authorization: Bearer {jwt}")
        self.assertNotIn(header, result)
        self.assertIn("***JWT_REDACTED***", result)

    def test_jwt_standalone(self) -> None:
        header = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9"
        payload = "eyJzdWIiOiJ1c2VyXzEyMyIsInJvbGUiOiJhZG1pbiJ9"
        sig = "abc123DEF456ghi789JKL012mno345PQR678stuVWX901yz"
        jwt = f"{header}.{payload}.{sig}"
        result = sanitize_text(jwt)
        self.assertIn("***JWT_REDACTED***", result)


class TestAzureSAS(unittest.TestCase):
    """Azure SAS token redaction."""

    def test_azure_sas_sig_param(self) -> None:
        url = (
            "https://account.blob.core.windows.net/container/blob"
            "?sv=2020-08-04&se=2023-01-01&sig=ABCDEFGHIJKLMNOPabcdefghij1234567890%2B"
        )
        result = sanitize_text(url)
        self.assertNotIn("ABCDEFGHIJKLMNOPabcdefghij1234567890%2B", result)
        self.assertIn("sig=***", result)

    def test_azure_sas_ampersand_sig(self) -> None:
        query = "&sig=XYZabcdefghijklmnopqrstuvwxyz1234567890"
        result = sanitize_text(query)
        self.assertNotIn("XYZabcdefghijklmnopqrstuvwxyz1234567890", result)
        self.assertIn("sig=***", result)


class TestHashiCorpVault(unittest.TestCase):
    """HashiCorp Vault service token (hvs.) redaction."""

    def test_hvs_vault_token(self) -> None:
        token = "hvs.ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
        result = sanitize_text(f"VAULT_TOKEN={token}")
        self.assertNotIn(token, result)
        self.assertIn("hvs.***", result)

    def test_hvs_in_env_export(self) -> None:
        token = "hvs.CAESIAbcdefghijklmnopqrstuvwxyz1234"
        result = sanitize_text(f"export VAULT_TOKEN={token}")
        self.assertNotIn(token, result)
        self.assertIn("hvs.***", result)


class TestDockerPAT(unittest.TestCase):
    """Docker personal access token (dckr_pat_) redaction."""

    def test_dckr_pat_token(self) -> None:
        token = "dckr_pat_ABCDEFGHIJKLMNOPabcdefghij1234"
        result = sanitize_text(f"DOCKER_TOKEN={token}")
        self.assertNotIn(token, result)
        self.assertIn("dckr_pat_***", result)


class TestDatabaseDSN(unittest.TestCase):
    """Database connection string (DSN) credential redaction."""

    def test_postgres_dsn(self) -> None:
        dsn = "postgres://alice:supersecretpassword@db.example.com:5432/mydb"
        result = sanitize_text(dsn)
        self.assertNotIn("supersecretpassword", result)
        self.assertIn("postgres://alice:***@", result)

    def test_mysql_dsn(self) -> None:
        dsn = "mysql://root:p@$$w0rd@localhost/production"
        result = sanitize_text(dsn)
        self.assertNotIn("p@$$w0rd", result)

    def test_mongodb_dsn(self) -> None:
        dsn = "mongodb://admin:MongoSecret123@cluster0.mongodb.net/test"
        result = sanitize_text(dsn)
        self.assertNotIn("MongoSecret123", result)
        self.assertIn("mongodb://admin:***@", result)

    def test_redis_dsn(self) -> None:
        dsn = "redis://default:RedisPass456@cache.example.com:6379/0"
        result = sanitize_text(dsn)
        self.assertNotIn("RedisPass456", result)
        self.assertIn("redis://default:***@", result)

    def test_postgresqlcompat_dsn(self) -> None:
        dsn = "postgresql://user:pa$$word@host/db"
        result = sanitize_text(dsn)
        self.assertNotIn("pa$$word", result)


class TestPEMPrivateKey(unittest.TestCase):
    """PEM private key block redaction."""

    _RSA_KEY = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA0Z3VS5JJcds3xHn/ygWep4PAtEsHAu+u\n"
        "fakefakefakefakefakefakefakefakefakefakefakefake\n"
        "-----END RSA PRIVATE KEY-----"
    )

    _EC_KEY = (
        "-----BEGIN EC PRIVATE KEY-----\nMHQCAQEEIOaFmckPiSt9rHKFakeKeyDataHereABC123\n-----END EC PRIVATE KEY-----"
    )

    _PKCS8_KEY = (
        "-----BEGIN PRIVATE KEY-----\n"
        "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDFakeDataFakeData\n"
        "-----END PRIVATE KEY-----"
    )

    def test_rsa_private_key_redacted(self) -> None:
        result = sanitize_text(self._RSA_KEY)
        self.assertNotIn("MIIEowIBAAKCAQEA", result)
        self.assertIn("***PEM_KEY_REDACTED***", result)

    def test_ec_private_key_redacted(self) -> None:
        result = sanitize_text(self._EC_KEY)
        self.assertNotIn("MHQCAQEEIOaFmckP", result)
        self.assertIn("***PEM_KEY_REDACTED***", result)

    def test_pkcs8_private_key_redacted(self) -> None:
        result = sanitize_text(self._PKCS8_KEY)
        self.assertNotIn("MIIEvgIBADANBgkq", result)
        self.assertIn("***PEM_KEY_REDACTED***", result)

    def test_pem_embedded_in_text(self) -> None:
        text = f"Config loaded.\n{self._RSA_KEY}\nServer started."
        result = sanitize_text(text)
        self.assertIn("***PEM_KEY_REDACTED***", result)
        self.assertIn("Config loaded.", result)
        self.assertIn("Server started.", result)


class TestBearerToken(unittest.TestCase):
    """Authorization: Bearer token redaction."""

    def test_bearer_in_header(self) -> None:
        header = "Authorization: Bearer eyABC123DEFxyz456GHI789"
        result = sanitize_text(header)
        self.assertNotIn("eyABC123DEFxyz456GHI789", result)
        self.assertIn("Bearer ***", result)

    def test_bearer_case_insensitive(self) -> None:
        header = "authorization: bearer mysupersecrettoken999"
        result = sanitize_text(header)
        self.assertNotIn("mysupersecrettoken999", result)

    def test_bearer_with_cli_flag(self) -> None:
        cmd = "--token my_secret_cli_token"
        result = sanitize_text(cmd)
        self.assertNotIn("my_secret_cli_token", result)
        self.assertIn("--token ***", result)


class TestKeyValuePatterns(unittest.TestCase):
    """Generic key=value / key: value patterns."""

    def test_api_key_equals(self) -> None:
        result = sanitize_text("api_key=abc123XYZsecretvalue")
        self.assertNotIn("abc123XYZsecretvalue", result)
        self.assertIn("***", result)

    def test_token_colon(self) -> None:
        result = sanitize_text("token: verysecrettoken12345")
        self.assertNotIn("verysecrettoken12345", result)
        self.assertIn("***", result)

    def test_password_equals(self) -> None:
        result = sanitize_text("password=hunter2isweakpassword")
        self.assertNotIn("hunter2isweakpassword", result)
        self.assertIn("***", result)

    def test_secret_colon(self) -> None:
        result = sanitize_text("secret: topsecretvalue9999")
        self.assertNotIn("topsecretvalue9999", result)
        self.assertIn("***", result)

    def test_api_key_cli_flag(self) -> None:
        result = sanitize_text("--api-key my-api-key-here")
        self.assertNotIn("my-api-key-here", result)
        self.assertIn("--api-key ***", result)


class TestOtherTokenTypes(unittest.TestCase):
    """GitLab, npm, HuggingFace, Stripe, Twilio, SendGrid, Google tokens."""

    def test_gitlab_pat(self) -> None:
        token = "glpat-ABCDEFGHIJKLMNOPqrstu"
        result = sanitize_text(token)
        self.assertNotIn(token, result)
        self.assertIn("glpat-***", result)

    def test_npm_token(self) -> None:
        token = "npm_ABCDEFGHIJKLMNOPQRSTuvwx"
        result = sanitize_text(token)
        self.assertNotIn(token, result)
        self.assertIn("npm_***", result)

    def test_huggingface_token(self) -> None:
        token = "hf_ABCDEFGHIJKLMNOPQRSTuvwx"
        result = sanitize_text(token)
        self.assertNotIn(token, result)
        self.assertIn("hf_***", result)

    def test_stripe_secret_key(self) -> None:
        # Use sk_test_ prefix (not sk_live_) to avoid GitHub push protection
        token = "sk_test_" + "X" * 24
        result = sanitize_text(token)
        self.assertNotIn(token, result)

    def test_stripe_restricted_key(self) -> None:
        token = "rk_test_" + "Y" * 24
        result = sanitize_text(token)
        self.assertNotIn(token, result)

    def test_twilio_account_sid(self) -> None:
        sid = "AC" + "a" * 32
        result = sanitize_text(sid)
        self.assertNotIn(sid, result)
        self.assertIn("AC_twilio_***", result)

    def test_twilio_auth_token(self) -> None:
        tok = "SK" + "b" * 32
        result = sanitize_text(tok)
        self.assertNotIn(tok, result)
        self.assertIn("SK_twilio_***", result)

    def test_sendgrid_api_key(self) -> None:
        key = "SG.ABCDEFGHIJKLMNOPQRSTuv.XYZabcdefghijklmnopqrst"
        result = sanitize_text(key)
        self.assertNotIn(key, result)
        self.assertIn("SG.***", result)

    def test_google_api_key(self) -> None:
        key = "AIzaSyABC123defGHI456jklMNO789pqrSTU"
        result = sanitize_text(key)
        self.assertNotIn(key, result)
        self.assertIn("AIza***", result)


class TestInnocuousText(unittest.TestCase):
    """Plain text without secrets must pass through unchanged."""

    def test_plain_sentence(self) -> None:
        text = "The quick brown fox jumps over the lazy dog."
        self.assertEqual(sanitize_text(text), text)

    def test_code_comment(self) -> None:
        text = "# This is a Python comment with no secrets"
        self.assertEqual(sanitize_text(text), text)

    def test_empty_string(self) -> None:
        self.assertEqual(sanitize_text(""), "")

    def test_log_line(self) -> None:
        text = "2024-01-01 12:00:00 INFO server started on port 8080"
        self.assertEqual(sanitize_text(text), text)

    def test_url_without_credentials(self) -> None:
        text = "https://api.example.com/v1/users?page=2&limit=50"
        self.assertEqual(sanitize_text(text), text)

    def test_number_sequence(self) -> None:
        text = "order_id=12345 user_id=67890"
        self.assertEqual(sanitize_text(text), text)

    def test_chinese_text(self) -> None:
        text = "这是普通的中文文本，没有任何敏感信息。"
        self.assertEqual(sanitize_text(text), text)


class TestSecretReplacementsStructure(unittest.TestCase):
    """Validate the _SECRET_REPLACEMENTS list structure."""

    def test_is_list(self) -> None:
        self.assertIsInstance(_SECRET_REPLACEMENTS, list)

    def test_each_entry_is_tuple_of_two(self) -> None:
        for entry in _SECRET_REPLACEMENTS:
            self.assertEqual(len(entry), 2, f"Entry {entry!r} should be a 2-tuple")

    def test_each_pattern_is_compiled(self) -> None:
        import re

        for pattern, _ in _SECRET_REPLACEMENTS:
            self.assertIsInstance(pattern, re.Pattern)

    def test_each_replacement_is_str(self) -> None:
        for _, repl in _SECRET_REPLACEMENTS:
            self.assertIsInstance(repl, str)

    def test_non_empty(self) -> None:
        self.assertGreater(len(_SECRET_REPLACEMENTS), 0)


class TestSanitizeTextIdempotent(unittest.TestCase):
    """Applying sanitize_text twice should produce the same result as once."""

    def test_idempotent_on_openai_key(self) -> None:
        text = "sk-abcdefghijklmnopqrstuvwx"
        once = sanitize_text(text)
        twice = sanitize_text(once)
        self.assertEqual(once, twice)

    def test_idempotent_on_github_token(self) -> None:
        token = "ghp_" + "A" * 36
        once = sanitize_text(token)
        twice = sanitize_text(once)
        self.assertEqual(once, twice)

    def test_idempotent_on_aws_key(self) -> None:
        key = "AKIAIOSFODNN7EXAMPLE1234"
        once = sanitize_text(key)
        twice = sanitize_text(once)
        self.assertEqual(once, twice)


class TestMultipleSecretsInOneString(unittest.TestCase):
    """A single string containing multiple secret types."""

    def test_openai_and_github_in_one_string(self) -> None:
        sk = "sk-abcdefghijklmnopqrstuvwx"
        ghp = "ghp_" + "Z" * 36
        text = f"OPENAI_KEY={sk} GITHUB_TOKEN={ghp}"
        result = sanitize_text(text)
        self.assertNotIn(sk, result)
        self.assertNotIn(ghp, result)
        self.assertIn("sk-***", result)
        self.assertIn("ghp_***", result)

    def test_aws_and_db_dsn_in_one_string(self) -> None:
        aws = "AKIAIOSFODNN7EXAMPLE1234"
        dsn = "postgres://bob:secretpass@db.local/app"
        text = f"key={aws} url={dsn}"
        result = sanitize_text(text)
        self.assertNotIn(aws, result)
        self.assertNotIn("secretpass", result)


if __name__ == "__main__":
    unittest.main()
