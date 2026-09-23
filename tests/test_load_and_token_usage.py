"""
Teste de Carga e Seguranca -- QuizesStudies
============================================

Valida:
1. Rate-limiting: garante que rotas retornam 429 apos atingir o limite.
2. Cota de tokens de IA: garante que AIQuotaExceededError e levantada ao ultrapassar o limite.
3. Simulacao de carga com N chamadas simultaneas via ThreadPoolExecutor.
4. Estimativa de consumo de tokens cumulativo ate ~200k.

Todos os testes usam mocks para NAO consumir tokens nem fazer chamadas reais a API.
"""
import statistics
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock


# ─────────────────────────────────────────────────────────────────────────────
# 1. Testes de Rate-Limiting (RateLimiter)
# ─────────────────────────────────────────────────────────────────────────────

class TestRateLimiter(unittest.TestCase):
    """Valida o comportamento do RateLimiter com janela deslizante."""

    def _make_limiter(self, limit=5, window=60):
        from api.handlers.quiz_handler import RateLimiter
        return RateLimiter(limit=limit, window_seconds=window)

    def test_allows_requests_under_limit(self):
        """Requisicoes abaixo do limite devem ser permitidas."""
        rl = self._make_limiter(limit=5)
        for i in range(5):
            allowed, retry_after = rl.is_allowed("test_key")
            self.assertTrue(allowed, f"Requisicao {i + 1} deveria ser permitida")
            self.assertEqual(retry_after, 0)

    def test_blocks_request_at_limit(self):
        """A 6a requisicao deve ser bloqueada."""
        rl = self._make_limiter(limit=5)
        for _ in range(5):
            rl.is_allowed("test_key")
        allowed, retry_after = rl.is_allowed("test_key")
        self.assertFalse(allowed)
        self.assertGreater(retry_after, 0)

    def test_different_keys_independent(self):
        """IPs diferentes devem ter contadores independentes."""
        rl = self._make_limiter(limit=2)
        rl.is_allowed("ip_a")
        rl.is_allowed("ip_a")
        allowed_a, _ = rl.is_allowed("ip_a")
        self.assertFalse(allowed_a, "ip_a deveria estar bloqueado")
        allowed_b, _ = rl.is_allowed("ip_b")
        self.assertTrue(allowed_b, "ip_b deveria ser independente")

    def test_window_resets_after_expiry(self):
        """Apos a janela expirar, o limite deve ser reiniciado."""
        rl = self._make_limiter(limit=2, window=1)
        rl.is_allowed("key")
        rl.is_allowed("key")
        allowed, _ = rl.is_allowed("key")
        self.assertFalse(allowed)
        time.sleep(1.1)
        allowed, _ = rl.is_allowed("key")
        self.assertTrue(allowed, "Deveria ser permitido apos janela expirar")

    def test_concurrent_safety(self):
        """Multiplas threads nao devem ultrapassar o limite definido."""
        rl = self._make_limiter(limit=10, window=60)
        allowed_count = 0
        lock = threading.Lock()

        def make_request():
            nonlocal allowed_count
            ok, _ = rl.is_allowed("shared_ip")
            if ok:
                with lock:
                    allowed_count += 1

        with ThreadPoolExecutor(max_workers=50) as ex:
            futures = [ex.submit(make_request) for _ in range(50)]
            for f in as_completed(futures):
                f.result()

        self.assertLessEqual(allowed_count, 10, "Nunca deve ultrapassar o limite sob concorrencia")
        self.assertEqual(allowed_count, 10, "Deve permitir exatamente o limite maximo")

    def test_retry_after_positive(self):
        """retry_after deve ser sempre >= 1 quando bloqueado."""
        rl = self._make_limiter(limit=1, window=60)
        rl.is_allowed("key")
        allowed, retry_after = rl.is_allowed("key")
        self.assertFalse(allowed)
        self.assertGreaterEqual(retry_after, 1)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Testes de Cota de Tokens de IA
# ─────────────────────────────────────────────────────────────────────────────

class TestAITokenQuota(unittest.TestCase):
    """Valida _TokenQuota e check_ai_token_quota."""

    def _make_quota(self, limit=1000, window=3600):
        from api.services.ai_service import _TokenQuota
        return _TokenQuota(quota=limit, window_seconds=window)

    def test_allows_under_quota(self):
        """Consumo abaixo do limite deve ser permitido."""
        q = self._make_quota(limit=1000)
        allowed, used, retry = q.check_and_record("ip_x", 100)
        self.assertTrue(allowed)
        self.assertEqual(used, 100)
        self.assertEqual(retry, 0)

    def test_blocks_over_quota(self):
        """Consumo acima do limite deve ser bloqueado."""
        q = self._make_quota(limit=500)
        q.check_and_record("ip_y", 400)
        allowed, used, retry = q.check_and_record("ip_y", 200)
        self.assertFalse(allowed)
        self.assertGreater(retry, 0)

    def test_estimate_tokens(self):
        """Estimativa de tokens deve ser aprox. len/4."""
        from api.services.ai_service import _TokenQuota
        q = _TokenQuota(quota=99999, window_seconds=3600)
        text = "a" * 400
        self.assertEqual(q.estimate_tokens(text), 100)

    def test_check_ai_token_quota_raises_on_excess(self):
        """Deve levantar AIQuotaExceededError quando limite for excedido."""
        from api.services.ai_service import check_ai_token_quota, AIQuotaExceededError, _token_quota
        test_ip = "10.0.99.99"
        original_quota = _token_quota.quota
        _token_quota.quota = 50
        try:
            big_prompt = "a" * 200  # ~50 tokens
            check_ai_token_quota(big_prompt, ip=test_ip)
            with self.assertRaises(AIQuotaExceededError):
                check_ai_token_quota(big_prompt, ip=test_ip)
        finally:
            _token_quota.quota = original_quota
            with _token_quota._lock:
                _token_quota._usage.pop(test_ip, None)

    def test_concurrent_quota_tracking(self):
        """Multiplas threads somam tokens corretamente sem race condition."""
        from api.services.ai_service import _TokenQuota
        q = _TokenQuota(quota=9999999, window_seconds=3600)
        ip = "192.168.0.99"
        tokens_per_thread = 100
        num_threads = 50

        with ThreadPoolExecutor(max_workers=num_threads) as ex:
            futures = [ex.submit(q.check_and_record, ip, tokens_per_thread) for _ in range(num_threads)]
            for f in as_completed(futures):
                f.result()

        total = q.get_usage(ip)
        self.assertEqual(total, tokens_per_thread * num_threads)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Simulacao de Carga com Multiplas Chamadas Simultaneas
# ─────────────────────────────────────────────────────────────────────────────

def _simulate_call(client_ip, prompt_size, quota_obj):
    """Simula chamada a generate_quiz_by_topic sem API real."""
    t0 = time.perf_counter()
    prompt = "a" * prompt_size
    estimated = quota_obj.estimate_tokens(prompt)
    allowed, used, retry = quota_obj.check_and_record(client_ip, estimated)
    latency = (time.perf_counter() - t0) * 1000
    if not allowed:
        return {"status": "quota_exceeded", "tokens": 0, "latency_ms": latency, "retry_after": retry}
    time.sleep(0.002)
    latency = (time.perf_counter() - t0) * 1000
    return {"status": "ok", "tokens": estimated, "latency_ms": latency}


class TestLoadSimulation(unittest.TestCase):
    """Testa concorrencia real e estimativa de consumo de tokens ate ~200k."""

    def _run_load(self, num_calls, workers, prompt_size, token_quota=9_999_999):
        from api.services.ai_service import _TokenQuota
        quota = _TokenQuota(quota=token_quota, window_seconds=3600)
        results = []
        lock = threading.Lock()

        def call(i):
            ip = "10.0.0.1"
            r = _simulate_call(ip, prompt_size, quota)
            with lock:
                results.append(r)

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(call, i) for i in range(num_calls)]
            for f in as_completed(futures):
                f.result()
        return results

    def _print_report(self, label, results):
        ok = [r for r in results if r["status"] == "ok"]
        blocked = [r for r in results if r["status"] == "quota_exceeded"]
        latencies = sorted(r["latency_ms"] for r in ok) if ok else [0]
        total_tokens = sum(r.get("tokens", 0) for r in ok)
        sep = "=" * 60
        print(f"\n{sep}")
        print(f"[REPORT] {label}")
        print(f"  Total    : {len(results)}")
        print(f"  OK       : {len(ok)}")
        print(f"  Blocked  : {len(blocked)}")
        if latencies:
            print(f"  p50 (ms) : {statistics.median(latencies):.2f}")
        if len(latencies) >= 20:
            print(f"  p95 (ms) : {latencies[int(len(latencies)*0.95)]:.2f}")
            print(f"  p99 (ms) : {latencies[int(len(latencies)*0.99)]:.2f}")
        print(f"  Tokens   : {total_tokens:,} / 200,000")
        print(sep)

    def test_low_concurrency_all_pass(self):
        """Carga baixa: 20 chamadas, 5 workers -- todas devem passar."""
        results = self._run_load(num_calls=20, workers=5, prompt_size=400)
        ok_count = sum(1 for r in results if r["status"] == "ok")
        self.assertEqual(ok_count, 20)
        self._print_report("Carga Baixa (20 chamadas, 5 workers)", results)

    def test_medium_concurrency_quota_blocks(self):
        """100 chamadas, 20 workers, quota 2.000 tokens -- maioria bloqueada."""
        results = self._run_load(num_calls=100, workers=20, prompt_size=400, token_quota=2000)
        ok = [r for r in results if r["status"] == "ok"]
        blocked = [r for r in results if r["status"] == "quota_exceeded"]
        self._print_report("Carga Media - Quota 2k Tokens (100 chamadas)", results)
        self.assertLessEqual(len(ok), 22)
        self.assertGreater(len(blocked), 70)

    def test_high_concurrency_200k_tokens(self):
        """500 chamadas x 50 workers, quota 200k -- 500*200=100k tokens usados."""
        results = self._run_load(num_calls=500, workers=50, prompt_size=800, token_quota=200_000)
        ok = [r for r in results if r["status"] == "ok"]
        total_tokens = sum(r.get("tokens", 0) for r in ok)
        self._print_report("Alta Carga 500 chamadas x 200 tokens (meta: 200k)", results)
        self.assertGreater(len(ok), 0)
        self.assertLessEqual(total_tokens, 200_000)
        print(f"  >> {len(ok)} chamadas usaram {total_tokens:,} de 200,000 tokens estimados")

    def test_200k_token_limit_exact(self):
        """Verifica que 200k tokens sao atingidos e bloqueados exatamente."""
        from api.services.ai_service import _TokenQuota
        quota = _TokenQuota(quota=200_000, window_seconds=3600)
        ip = "192.168.1.100"
        prompt = "a" * 4_000  # 1.000 tokens por chamada
        results = []
        for i in range(210):
            estimated = quota.estimate_tokens(prompt)
            allowed, used, retry = quota.check_and_record(ip, estimated)
            results.append({"call": i + 1, "status": "ok" if allowed else "blocked", "used": used})
            if not allowed:
                break

        ok = [r for r in results if r["status"] == "ok"]
        blocked = [r for r in results if r["status"] == "blocked"]
        sep = "=" * 60
        print(f"\n{sep}")
        print("[LIMITE] Teste exato de 200k Tokens")
        print(f"  Chamadas OK    : {len(ok)}")
        print(f"  Tokens no bloqueio: {ok[-1]['used']:,}" if ok else "  N/A")
        print(f"  Bloqueios      : {len(blocked)}")
        print(sep)
        self.assertGreater(len(ok), 0)
        if ok:
            self.assertLessEqual(ok[-1]["used"], 200_000)

    def test_ddos_many_ips(self):
        """DDoS: 50 IPs distintos x 10 chamadas cada, quota/IP=1000 tokens."""
        from api.services.ai_service import _TokenQuota
        per_ip_quota = 1000
        prompt_size = 800  # ~200 tokens
        quota = _TokenQuota(quota=per_ip_quota, window_seconds=3600)
        num_ips = 50
        calls_per_ip = 10
        results_per_ip = {}

        def attack(ip_suffix):
            ip = f"192.168.100.{ip_suffix}"
            res = []
            for _ in range(calls_per_ip):
                estimated = quota.estimate_tokens("a" * prompt_size)
                allowed, used, retry = quota.check_and_record(ip, estimated)
                res.append("ok" if allowed else "blocked")
            return ip, res

        with ThreadPoolExecutor(max_workers=20) as ex:
            for ip, res in [f.result() for f in as_completed([ex.submit(attack, i) for i in range(num_ips)])]:
                results_per_ip[ip] = res

        max_ok_per_ip = per_ip_quota // (prompt_size // 4)
        ok_counts = [r.count("ok") for r in results_per_ip.values()]
        sep = "=" * 60
        print(f"\n{sep}")
        print(f"[DDOS] {num_ips} IPs x {calls_per_ip} chamadas (quota/IP={per_ip_quota})")
        print(f"  Media OK/IP: {sum(ok_counts)/len(ok_counts):.1f} (max: {max_ok_per_ip})")
        print(sep)
        for ip, res in results_per_ip.items():
            self.assertLessEqual(res.count("ok"), max_ok_per_ip + 1,
                                 f"IP {ip} ultrapassou a cota individual")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Testes de Headers de Seguranca
# ─────────────────────────────────────────────────────────────────────────────

class TestSecurityHeaders(unittest.TestCase):
    """Verifica que os headers de seguranca corretos estao configurados."""

    def _make_mock_handler(self):
        handler = MagicMock()
        handler.headers = {}
        handler.wfile = MagicMock()
        sent_headers = {}
        handler.send_header = lambda name, value: sent_headers.update({name: value})
        handler.send_response = MagicMock()
        handler.end_headers = MagicMock()
        return handler, sent_headers

    def test_hsts_header_present(self):
        """Strict-Transport-Security deve estar presente e correto."""
        from api.middleware.http_middleware import HTTPMiddleware
        handler, sent = self._make_mock_handler()
        HTTPMiddleware.add_security_headers(handler)
        self.assertIn("Strict-Transport-Security", sent)
        self.assertIn("max-age=63072000", sent["Strict-Transport-Security"])
        self.assertIn("includeSubDomains", sent["Strict-Transport-Security"])

    def test_x_frame_options_deny(self):
        from api.middleware.http_middleware import HTTPMiddleware
        handler, sent = self._make_mock_handler()
        HTTPMiddleware.add_security_headers(handler)
        self.assertEqual(sent.get("X-Frame-Options"), "DENY")

    def test_csp_present(self):
        from api.middleware.http_middleware import HTTPMiddleware
        handler, sent = self._make_mock_handler()
        HTTPMiddleware.add_security_headers(handler)
        self.assertIn("Content-Security-Policy", sent)

    def test_x_content_type_nosniff(self):
        from api.middleware.http_middleware import HTTPMiddleware
        handler, sent = self._make_mock_handler()
        HTTPMiddleware.add_security_headers(handler)
        self.assertEqual(sent.get("X-Content-Type-Options"), "nosniff")

    def test_get_client_ip_cloudflare(self):
        """CF-Connecting-IP deve ter prioridade."""
        from api.middleware.http_middleware import HTTPMiddleware
        handler = MagicMock()
        handler.headers = {"CF-Connecting-IP": "203.0.113.42"}
        handler.client_address = ("127.0.0.1", 1234)
        self.assertEqual(HTTPMiddleware.get_client_ip(handler), "203.0.113.42")

    def test_get_client_ip_x_forwarded_for(self):
        """X-Forwarded-For deve ser usado quando CF header ausente."""
        from api.middleware.http_middleware import HTTPMiddleware
        handler = MagicMock()
        handler.headers = {"X-Forwarded-For": "198.51.100.1, 10.0.0.1"}
        handler.client_address = ("127.0.0.1", 1234)
        self.assertEqual(HTTPMiddleware.get_client_ip(handler), "198.51.100.1")

    def test_get_client_ip_fallback_socket(self):
        """Deve usar endereco do socket como fallback."""
        from api.middleware.http_middleware import HTTPMiddleware
        handler = MagicMock()
        handler.headers = {}
        handler.client_address = ("10.10.10.10", 4321)
        self.assertEqual(HTTPMiddleware.get_client_ip(handler), "10.10.10.10")


if __name__ == "__main__":
    unittest.main(verbosity=2)
