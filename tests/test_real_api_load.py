"""
Teste REAL de Carga na API -- QuizesStudies
==========================================

AVISO: Este script faz chamadas REAIS ao servidor local (ou remoto) e
CONSUMIRA TOKENS REAIS da sua conta Gemini / OpenRouter.

Uso:
    python tests/test_real_api_load.py [opcoes]

Exemplos:
    # 5 chamadas, 1 worker (mais seguro para testar)
    python tests/test_real_api_load.py --calls 5 --workers 1

    # 20 chamadas, 4 workers simultaneos (consumo moderado)
    python tests/test_real_api_load.py --calls 20 --workers 4

    # Teste de rajada: 50 chamadas, 10 workers (verifica rate-limit)
    python tests/test_real_api_load.py --calls 50 --workers 10 --burst

    # Usar servidor remoto
    python tests/test_real_api_load.py --base-url https://meu-site.vercel.app --calls 10

Tokens estimados por chamada (3 questoes):
    ~800 tokens input  +  ~660 tokens output  =  ~1.460 tokens total
Tokens estimados por chamada (10 questoes):
    ~1.200 tokens input  +  ~2.200 tokens output  =  ~3.400 tokens total
"""

import argparse
import json
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

COST_INPUT_PER_1M = 0.075    # USD (OpenRouter Gemini Flash)
COST_OUTPUT_PER_1M = 0.300   # USD

TOPICS = [
    "Raciocinio Logico Proposicional",
    "Matematica Financeira",
    "Portugues - Interpretacao de Texto",
    "Direito Constitucional",
    "Informatica Basica",
    "Historia do Brasil",
    "Quimica Organica",
    "Fisica - Cinematica",
    "Biologia Celular",
    "Legislacao Tributaria",
    "Administracao Publica",
    "Economia Politica",
    "Geografia do Brasil",
    "Ingles - Reading Comprehension",
    "Estatistica Descritiva",
]


def is_quizes_server(base_url):
    """Verifica se a URL realmente pertence ao servidor QuizesStudies.
    Evita falsos positivos como Microsoft-HTTPAPI / IIS na porta 8000."""
    try:
        req = urllib.request.Request(f"{base_url}/api/quizzes", method="GET")
        with urllib.request.urlopen(req, timeout=2) as r:
            server_header = r.headers.get("Server", "")
            if "Microsoft-HTTPAPI" in server_header:
                return False
            body = r.read().decode("utf-8", errors="ignore")
            return "success" in body or r.headers.get("X-Content-Type-Options") == "nosniff"
    except urllib.error.HTTPError as e:
        server_header = e.headers.get("Server", "")
        if "Microsoft-HTTPAPI" in server_header:
            return False
        try:
            body = e.read().decode("utf-8", errors="ignore")
            data = json.loads(body)
            if "AUTH_REQUIRED" in body or "success" in data or e.headers.get("X-Content-Type-Options") == "nosniff":
                return True
        except Exception:
            pass
        return False
    except Exception:
        return False


def auto_detect_port(base_ports=(8001, 8002, 8000, 8003, 8004, 3000, 5000)):
    """Tenta encontrar a porta onde o servidor QuizesStudies esta rodando."""
    for port in base_ports:
        url = f"http://localhost:{port}"
        if is_quizes_server(url):
            return url
    return None


def validate_server(base_url):
    """Verifica se o servidor apontado responde como a aplicacao QuizesStudies."""
    return is_quizes_server(base_url)


def _http_post(url, payload, token=None, timeout=90):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Length": str(len(body)),
        "User-Agent": "QuizLoadTest/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            latency = (time.perf_counter() - t0) * 1000
            data = json.loads(resp.read().decode("utf-8"))
            return resp.status, data, latency
    except urllib.error.HTTPError as e:
        latency = (time.perf_counter() - t0) * 1000
        try:
            data = json.loads(e.read().decode("utf-8"))
        except Exception:
            data = {"error": str(e)}
        return e.code, data, latency
    except Exception as e:
        latency = (time.perf_counter() - t0) * 1000
        return 0, {"error": str(e)}, latency


def _http_get(url, token=None, timeout=30):
    headers = {
        "User-Agent": "QuizLoadTest/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            latency = (time.perf_counter() - t0) * 1000
            data = json.loads(resp.read().decode("utf-8"))
            return resp.status, data, latency
    except urllib.error.HTTPError as e:
        latency = (time.perf_counter() - t0) * 1000
        try:
            data = json.loads(e.read().decode("utf-8"))
        except Exception:
            data = {"error": str(e)}
        return e.code, data, latency
    except Exception as e:
        latency = (time.perf_counter() - t0) * 1000
        return 0, {"error": str(e)}, latency


def run_single_call(call_id, base_url, num_questions, token, is_guest, endpoint="generate"):
    topic = TOPICS[call_id % len(TOPICS)]
    
    if endpoint == "quizzes":
        url = f"{base_url}/api/quizzes"
        status, data, latency = _http_get(url, token=token)
        result = {
            "call_id": call_id + 1,
            "topic": "GET /api/quizzes",
            "status": status,
            "latency_ms": latency,
            "real_prompt_tokens": 0,
            "real_completion_tokens": 0,
            "real_total_tokens": 0,
            "model": "API Local",
            "success": status in (200, 201),
            "rate_limited": status == 429,
            "error": None,
            "questions_generated": 0,
        }
        if not result["success"]:
            if status == 429:
                retry_after = data.get("retry_after") or "?"
                result["error"] = f"429 Rate Limited (Retry-After: {retry_after}s)"
            elif status == 0:
                result["error"] = data.get("error", "Conexão recusada")
            else:
                result["error"] = data.get("message") or data.get("error") or f"HTTP {status}"
        return result

    # Endpoint padrão: generate (IA)
    guest_param = "?guest=1" if is_guest else ""
    url = f"{base_url}/api/quiz/generate{guest_param}"
    payload = {
        "topic": topic,
        "num_questions": num_questions,
        "difficulty": ["Facil", "Medio", "Dificil"][call_id % 3],
    }
    status, data, latency = _http_post(url, payload, token=token)
    api_data = data.get("data") if isinstance(data.get("data"), dict) else data
    usage = api_data.get("usage") or {}
    real_prompt = int(usage.get("prompt_tokens") or 0)
    real_comp = int(usage.get("completion_tokens") or 0)
    real_tot = int(usage.get("total_tokens") or (real_prompt + real_comp))
    model_name = api_data.get("model") or api_data.get("provider") or "IA"

    result = {
        "call_id": call_id + 1,
        "topic": topic,
        "status": status,
        "latency_ms": latency,
        "real_prompt_tokens": real_prompt,
        "real_completion_tokens": real_comp,
        "real_total_tokens": real_tot,
        "model": model_name,
        "success": status in (200, 201),
        "rate_limited": status == 429,
        "error": None,
        "questions_generated": 0,
    }
    if result["success"]:
        questions = data.get("questions") or api_data.get("questions", [])
        result["questions_generated"] = len(questions)
    elif status == 429:
        retry_after = data.get("retry_after") or "?"
        result["error"] = f"429 Rate Limited (Retry-After: {retry_after}s)"
    elif status == 0:
        result["error"] = data.get("error", "Conexao recusada - servidor off?")
    else:
        result["error"] = data.get("message") or data.get("error") or f"HTTP {status}"
    return result


def print_live(result, cumulative_tokens, token_limit, endpoint="generate"):
    ts = datetime.now().strftime("%H:%M:%S")
    if result["success"]:
        status_str = f"[OK {result['status']}]"
        if endpoint == "quizzes":
            detail = f"OK | {result['latency_ms']:.0f}ms"
        else:
            if result["real_total_tokens"] > 0:
                tk_str = f"Tokens reais: {result['real_total_tokens']:,}"
            else:
                tk_str = "Tokens: N/A"
            detail = f"{result['questions_generated']}q geradas | {result['latency_ms']:.0f}ms | {tk_str} ({result['model']})"
    elif result["rate_limited"]:
        status_str = "[429 BLOCKED]"
        detail = result["error"]
    else:
        status_str = f"[ERR {result['status']}]"
        detail = str(result.get("error", ""))[:60]

    if endpoint == "generate" and token_limit > 0:
        pct = min(100.0, (cumulative_tokens / token_limit * 100))
        bar_done = int(pct / 5)
        bar = "#" * bar_done + "." * (20 - bar_done)
        print(f"  {ts} #{result['call_id']:>3} {status_str:<14} {result['topic'][:28]:<28} | {detail}")
        if cumulative_tokens > 0:
            print(f"            Tokens reais acumulados: {cumulative_tokens:>9,} / {token_limit:,}  [{bar}] {pct:.1f}%")
    else:
        print(f"  {ts} #{result['call_id']:>3} {status_str:<14} {result['topic'][:28]:<28} | {detail}")


def run_load_test(base_url, num_calls, workers, num_questions,
                  burst, token, is_guest, token_limit, endpoint="generate"):
    sep = "=" * 72
    print(f"\n{sep}")
    print(f"  TESTE REAL DE CARGA -- QuizesStudies")
    print(f"  Servidor   : {base_url}")
    print(f"  Endpoint   : {'POST /api/quiz/generate (IA)' if endpoint == 'generate' else 'GET /api/quizzes (Sem consumo de IA)'}")
    print(f"  Chamadas   : {num_calls}  |  Workers: {workers}")
    if endpoint == "generate":
        print(f"  Questoes   : {num_questions} por chamada")
        print(f"  Limite cota: {token_limit:,} tokens")
    print(f"  Modo       : {'RAJADA (sem sleep)' if burst else 'Normal (0.3s entre lotes)'}")
    print(f"  Auth       : {'Bearer token' if token else 'Guest / sem autenticacao'}")
    print()
    if endpoint == "generate":
        print(f"  !!! AVISO: Chamadas reais a API de IA. Ctrl+C para abortar. !!!")
    print(f"{sep}\n")

    results = []
    cumulative_tokens = 0
    lock = threading.Lock()
    stop_flag = threading.Event()

    def call_worker(call_id):
        nonlocal cumulative_tokens
        if stop_flag.is_set():
            return None
        if not burst and workers > 1 and call_id > 0:
            time.sleep(0.3)
        result = run_single_call(call_id, base_url, num_questions, token, is_guest, endpoint=endpoint)
        with lock:
            cumulative_tokens += result["real_total_tokens"]
            results.append(result)
            print_live(result, cumulative_tokens, token_limit, endpoint=endpoint)
            if token_limit > 0 and cumulative_tokens >= token_limit:
                print(f"\n  [LIMITE] {token_limit:,} tokens atingidos -- parando.")
                stop_flag.set()
        return result

    start = time.perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(call_worker, i) for i in range(num_calls)]
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception:
                    pass
    except KeyboardInterrupt:
        stop_flag.set()
        print("\n  [ABORTADO pelo usuario]")

    elapsed = time.perf_counter() - start

    ok = [r for r in results if r and r["success"]]
    blocked = [r for r in results if r and r["rate_limited"]]
    errors = [r for r in results if r and not r["success"] and not r["rate_limited"]]
    latencies = sorted(r["latency_ms"] for r in ok) if ok else [0]
    total_questions = sum(r["questions_generated"] for r in ok)
    total_tokens = sum(r["real_total_tokens"] for r in ok)
    total_input = sum(r["real_prompt_tokens"] for r in ok)
    total_output = sum(r["real_completion_tokens"] for r in ok)

    print(f"\n{sep}")
    print(f"  RELATORIO FINAL")
    print(f"  Duracao total     : {elapsed:.1f}s")
    print(f"  Chamadas feitas   : {len(results)} / {num_calls}")
    print(f"  Sucesso (OK)      : {len(ok)}")
    print(f"  Bloqueadas (429)  : {len(blocked)}")
    print(f"  Erros             : {len(errors)}")
    if endpoint == "generate":
        print(f"  Questoes geradas  : {total_questions}")
    print()
    if ok:
        print(f"  Latencia:")
        print(f"    p50 : {statistics.median(latencies):.0f}ms")
        if len(latencies) >= 3:
            print(f"    p95 : {latencies[max(0, int(len(latencies)*0.95)-1)]:.0f}ms")
        print(f"    max : {max(latencies):.0f}ms")
    print()
    if endpoint == "generate":
        if total_tokens > 0:
            cost_usd = (total_input / 1_000_000 * COST_INPUT_PER_1M) + \
                       (total_output / 1_000_000 * COST_OUTPUT_PER_1M)
            print(f"  Tokens REAIS reportados pela API:")
            print(f"    Input (Prompt)     : {total_input:,}")
            print(f"    Output (Completion): {total_output:,}")
            print(f"    TOTAL              : {total_tokens:,}")
            print(f"  Custo estimado (se via OpenRouter): ~${cost_usd:.5f} USD")
            print(f"  (Obs: Se via Google AI Studio direto, e 100% gratuito dentro da cota)")
        else:
            print(f"  Tokens: O provedor de IA nao retornou contagem no payload.")
    print(sep)
    return len(ok) > 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Teste de carga REAL na API QuizesStudies"
    )
    parser.add_argument("--base-url", default=None,
                        help="URL base do servidor. Se omitido, detecta automaticamente.")
    parser.add_argument("--calls", type=int, default=3)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--questions", type=int, default=3)
    parser.add_argument("--endpoint", choices=["generate", "quizzes"], default="generate",
                        help="'generate' (IA) ou 'quizzes' (leitura rapida sem consumo de tokens)")
    parser.add_argument("--token-limit", type=int, default=200_000)
    parser.add_argument("--burst", action="store_true")
    parser.add_argument("--guest", action="store_true")
    parser.add_argument("--token", default=None)
    args = parser.parse_args()

    if not (1 <= args.questions <= 20):
        print("ERRO: --questions deve ser entre 1 e 20")
        sys.exit(1)

    # Auto-detectar porta se nao especificado
    base_url = args.base_url
    if not base_url:
        print("Detectando servidor...")
        base_url = auto_detect_port()
        if base_url:
            print(f"Servidor encontrado em: {base_url}")
        else:
            print("ERRO: Servidor nao encontrado nas portas 8000-8003, 3000, 5000.")
            print("Execute 'python quiz_api.py' em outro terminal e tente novamente.")
            print("Ou use: --base-url http://localhost:PORTA")
            sys.exit(1)
    else:
        if not validate_server(base_url):
            print(f"ERRO: Servidor nao acessivel em {base_url}")
            print("Verifique se o servidor esta rodando e a URL esta correta.")
            sys.exit(1)

    success = run_load_test(
        base_url=base_url,
        num_calls=args.calls,
        workers=min(args.workers, args.calls),
        num_questions=args.questions,
        burst=args.burst,
        token=args.token,
        is_guest=args.guest,
        token_limit=args.token_limit,
        endpoint=args.endpoint,
    )
    sys.exit(0 if success else 1)
