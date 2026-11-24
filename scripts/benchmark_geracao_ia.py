"""
Mede o tempo da geração por tema contra uma OpenAI simulada, sem gastar tokens.

A OpenAI falsa responde em partes (streaming) na velocidade publicada do modelo e espera antes
do primeiro trecho conforme o esforço de raciocínio pedido. Assim dá para comparar mudanças no
fluxo (partes, paralelismo, conferência, tamanho das respostas) antes de ir para produção.

Valores padrão (gpt-6-luna na OpenAI, Artificial Analysis, nov/2026): ~131 tokens/s e 0,74 s até
o primeiro token sem raciocínio; ~2,2 s com raciocínio "low"; ~5,3 s com o esforço padrão.
O tamanho das respostas imita o que o prompt pede: explicação de 2 a 4 frases e JSON indentado
(prompt antigo) ou explicação de 1 a 2 frases e JSON em uma linha (prompt novo). São estimativas:
o tempo real aparece em Minha conta → Diagnóstico da IA (média das últimas 24 h).

Uso:
    python scripts/benchmark_geracao_ia.py
    python scripts/benchmark_geracao_ia.py --tps 131 --ttft-none 0.74 --ttft-low 2.2 --sizes 5,10,20,30
"""

import argparse
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SPEED = {"tps": 131.0, "ttft": {"none": 0.74, "minimal": 0.9, "low": 2.2, "medium": 5.3, None: 5.3}}
CALLS: list[dict] = []
_calls_lock = threading.Lock()


def _sentence(n_words: int, seed: int) -> str:
    words = (
        "conceito",
        "regra",
        "aplicação",
        "resultado",
        "exemplo",
        "princípio",
        "condição",
        "valor",
        "definição",
        "propriedade",
        "caso",
        "efeito",
    )
    return " ".join(words[(seed + i) % len(words)] for i in range(n_words)).capitalize() + "."


def _fake_quiz(qty: int, compact: bool, part_hint: int) -> str:
    """JSON de questões com o tamanho típico de cada estilo de prompt."""
    questions = []
    for i in range(1, qty + 1):
        seed = part_hint * 100 + i
        q = {
            "id": i,
            "section": "Subtema",
            "question": f"Questão {seed}: " + _sentence(22, seed)[:-1] + "?",
            "options": [_sentence(7, seed + k) for k in range(4)],
            "answer": 0,
        }
        if compact:
            q["explanation"] = " ".join(_sentence(14, seed + k) for k in range(2))
        else:
            q["context"] = _sentence(18, seed + 7)
            q["explanation"] = " ".join(_sentence(16, seed + k) for k in range(3))
        questions.append(q)
    data = {"title": "Simulado de teste", "questions": questions}
    return json.dumps(data, ensure_ascii=False) if compact else json.dumps(data, ensure_ascii=False, indent=2)


class FakeOpenAI(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        prompt = (body.get("messages") or [{}])[-1].get("content", "")
        effort = body.get("reasoning_effort") or (body.get("reasoning") or {}).get("effort")
        started = time.monotonic()
        if "revisor rigoroso" in prompt:
            ids = [int(x) for x in re.findall(r'"id": (\d+)', prompt)]
            text = json.dumps({"answers": [{"id": i, "answer": 0} for i in ids]})
            kind = "check"
        else:
            qty = int(re.search(r"exatamente (\d+) quest", prompt).group(1))
            part = re.search(r"parte (\d+) de", prompt)
            compact = "uma linha só" in prompt
            text = _fake_quiz(qty, compact, int(part.group(1)) if part else 0)
            kind = "generate"
        tokens = max(1, len(text) // 4)
        time.sleep(SPEED["ttft"].get(effort, SPEED["ttft"][None]))
        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            step = 64  # caracteres por trecho
            delay = (step / 4) / SPEED["tps"]
            for i in range(0, len(text), step):
                chunk = {"choices": [{"delta": {"content": text[i : i + step]}}]}
                self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
                self.wfile.flush()
                time.sleep(delay)
            self.wfile.write(b"data: [DONE]\n\n")
        else:
            time.sleep(tokens / SPEED["tps"])
            raw = json.dumps({"choices": [{"message": {"content": text}}], "usage": {"total_tokens": tokens}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        with _calls_lock:
            CALLS.append(
                {"kind": kind, "effort": effort, "tokens": tokens, "seconds": round(time.monotonic() - started, 2)}
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tps", type=float, default=131.0, help="tokens de saída por segundo")
    parser.add_argument("--ttft-none", type=float, default=0.74)
    parser.add_argument("--ttft-low", type=float, default=2.2)
    parser.add_argument("--ttft-medium", type=float, default=5.3)
    parser.add_argument("--sizes", default="5,10,20,30")
    parser.add_argument("--no-cross-check", action="store_true", help="mede também sem a conferência")
    args = parser.parse_args()
    SPEED["tps"] = args.tps
    SPEED["ttft"].update(
        {"none": args.ttft_none, "low": args.ttft_low, "medium": args.ttft_medium, None: args.ttft_medium}
    )

    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenAI)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    os.environ.update(
        {
            "OPENAI_API_KEY": "teste-local",
            "OPENAI_BASE_URL": f"http://127.0.0.1:{server.server_address[1]}/v1",
            "OPENAI_MODELS": "gpt-6-luna",
            "AI_PROVIDERS": "openai",
            "AI_DAILY_CALL_LIMIT": "0",
            "AI_CACHE_TTL_DAYS": "0",
            "DATABASE_URL": "",
        }
    )
    from api.services import ai_service

    ai_service.ai_job_repo.cache_get = lambda key: None
    ai_service.ai_job_repo.cache_set = lambda key, result: None

    modes = [True] + ([False] if args.no_cross_check else [])
    print(
        f"OpenAI simulada: {args.tps:.0f} tokens/s; primeiro token {args.ttft_none}s (none) / "
        f"{args.ttft_low}s (low) / {args.ttft_medium}s (padrão)\n"
    )
    print(f"{'questões':>9} {'conferência':>12} {'tempo':>8} {'chamadas':>9} {'questões ok':>12}")
    for size in [int(s) for s in args.sizes.split(",")]:
        for cross_check in modes:
            CALLS.clear()
            started = time.monotonic()
            result = ai_service.generate_quiz_by_topic(
                f"Tema de teste {size} {cross_check} {time.time()}",
                num_questions=size,
                cross_check=cross_check,
            )
            elapsed = time.monotonic() - started
            print(
                f"{size:>9} {'sim' if cross_check else 'não':>12} {elapsed:>7.1f}s {len(CALLS):>9} "
                f"{len(result['questions']):>12}"
            )
    server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
