"""
Credenciais do banco independentes do provedor (Neon, Supabase, local).

1. URL: postgres:// normalizado, sslmode/sslrootcert/connect_timeout completados sem
   sobrescrever o que já está na URL; localhost intocado.
2. DATABASE_URL_DIRECT: ordem de escolha e proteção contra variável esquecida da integração.
3. Certificado em DB_SSLROOTCERT_PEM gravado em arquivo temporário.
4. Logs sem usuário/senha e aviso único de TLS que não valida o certificado.
"""
import importlib
import io
import os
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from api.database import connection
from api.utils import config


def _reload_config(env: dict):
    keys = (
        "DATABASE_URL", "POSTGRES_URL", "DATABASE_URL_UNPOOLED", "POSTGRES_PRISMA_URL",
        "POSTGRES_URL_NON_POOLING", "DATABASE_URL_DIRECT",
    )
    clean = {k: v for k, v in os.environ.items() if k not in keys}
    clean.update(env)
    with patch.dict(os.environ, clean, clear=True), \
         patch("dotenv.load_dotenv", lambda *a, **k: None):
        return importlib.reload(config)


class BuildDatabaseUrlTests(unittest.TestCase):
    def test_remote_url_gets_verify_full_with_system_ca(self):
        url = connection.build_database_url("postgres://u:p@ep-x-pooler.aws.neon.tech/neondb")
        self.assertTrue(url.startswith("postgresql://"))
        self.assertIn("sslmode=verify-full", url)
        self.assertIn("sslrootcert=system", url)
        self.assertIn("connect_timeout=5", url)

    def test_existing_sslmode_is_kept(self):
        url = connection.build_database_url("postgresql://u:p@h.example.com/db?sslmode=require")
        self.assertIn("sslmode=require", url)
        self.assertNotIn("verify-full", url)
        self.assertNotIn("sslrootcert", url)

    def test_existing_sslrootcert_is_kept(self):
        url = connection.build_database_url(
            "postgresql://u:p@h.example.com/db?sslmode=verify-full&sslrootcert=/x/ca.crt"
        )
        self.assertEqual(url.count("sslrootcert="), 1)
        self.assertIn("sslrootcert=/x/ca.crt", url)

    def test_configured_root_cert_is_used(self):
        with patch.object(connection, "DB_SSLROOTCERT", "/certs/supabase ca.crt"):
            url = connection.build_database_url("postgresql://u:p@aws-0-sa-east-1.pooler.supabase.com:6543/postgres")
        self.assertIn("sslrootcert=/certs/supabase%20ca.crt", url)

    def test_localhost_is_untouched(self):
        raw = "postgresql://postgres:x@localhost:5433/quiz_study"
        self.assertEqual(connection.build_database_url(raw), raw)

    def test_empty_url(self):
        self.assertEqual(connection.build_database_url(None), "")

    def test_pem_is_written_to_temp_file(self):
        pem = "-----BEGIN CERTIFICATE-----\\nABC\\n-----END CERTIFICATE-----"
        with patch.object(connection, "DB_SSLROOTCERT_PEM", pem), \
             patch.object(connection, "_pem_path", None):
            path = connection._sslrootcert()
            try:
                content = Path(path).read_text()
                self.assertIn("-----BEGIN CERTIFICATE-----\nABC\n", content)
                self.assertEqual(connection._sslrootcert(), path)  # reaproveita o arquivo
            finally:
                os.unlink(path)


class DescribeAndWarnTests(unittest.TestCase):
    def test_describe_hides_credentials(self):
        target = connection.describe_database_target("postgresql://user:segredo@h.supabase.com:6543/postgres")
        self.assertEqual(target, "h.supabase.com:6543/postgres")
        self.assertNotIn("segredo", target)
        self.assertNotIn("user", target)

    def test_weak_tls_warns_once_without_password(self):
        buf = io.StringIO()
        with patch.object(connection, "_tls_warning_shown", False), redirect_stderr(buf):
            connection._warn_if_weak_tls("postgresql://u:segredo@h.example.com/db?sslmode=require")
            connection._warn_if_weak_tls("postgresql://u:segredo@h.example.com/db?sslmode=require")
        out = buf.getvalue()
        self.assertEqual(out.count("Aviso"), 1)
        self.assertNotIn("segredo", out)

    def test_verify_full_does_not_warn(self):
        buf = io.StringIO()
        with patch.object(connection, "_tls_warning_shown", False), redirect_stderr(buf):
            connection._warn_if_weak_tls("postgresql://u:p@h.example.com/db?sslmode=verify-full")
        self.assertEqual(buf.getvalue(), "")


class DirectUrlResolutionTests(unittest.TestCase):
    def tearDown(self):
        importlib.reload(config)

    def test_explicit_direct_wins(self):
        cfg = _reload_config({
            "DATABASE_URL": "postgresql://app@pooler/db",
            "DATABASE_URL_DIRECT": "postgresql://app@direct/db",
        })
        self.assertEqual(cfg.DATABASE_URL_DIRECT, "postgresql://app@direct/db")

    def test_manual_database_url_ignores_leftover_integration_vars(self):
        cfg = _reload_config({
            "DATABASE_URL": "postgresql://novo@supabase/db",
            "DATABASE_URL_UNPOOLED": "postgresql://antigo@neon/db",
        })
        self.assertEqual(cfg.DATABASE_URL, "postgresql://novo@supabase/db")
        self.assertEqual(cfg.DATABASE_URL_DIRECT, "postgresql://novo@supabase/db")

    def test_integration_only_uses_unpooled_for_direct(self):
        cfg = _reload_config({
            "POSTGRES_URL": "postgresql://neon@pooler/db",
            "DATABASE_URL_UNPOOLED": "postgresql://neon@direct/db",
        })
        self.assertEqual(cfg.DATABASE_URL, "postgresql://neon@pooler/db")
        self.assertEqual(cfg.DATABASE_URL_DIRECT, "postgresql://neon@direct/db")

    def test_relative_root_cert_resolves_from_project_root(self):
        cfg = _reload_config({"DB_SSLROOTCERT": "certs/supabase-ca.crt"})
        self.assertEqual(Path(cfg.DB_SSLROOTCERT), config.ROOT / "certs" / "supabase-ca.crt")


if __name__ == "__main__":
    unittest.main()
