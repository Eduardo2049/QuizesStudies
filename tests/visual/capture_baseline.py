"""Captura screenshots das telas principais (baseline visual) usando o Edge ou o
Chrome já instalados, controlados pelo protocolo DevTools (CDP).

Só usa a biblioteca padrão: não precisa de Playwright nem de download de navegador.
Pelo CDP a largura do viewport é emulada de verdade (o Edge headless não aceita
janelas com menos de ~500px), o tema vem de `prefers-color-scheme` e a captura
pega a página inteira.

Uso (com o app rodando, ex.: http://127.0.0.1:8000):
    python tests/visual/capture_baseline.py --label before
    python tests/visual/capture_baseline.py --label after --base-url http://127.0.0.1:8000
    python tests/visual/capture_baseline.py --browser "C:/caminho/para/chrome.exe"
    python tests/visual/capture_baseline.py --only home,login

A home é capturada no modo convidado (/guest), então não precisa de login.
Saída: design-baseline/<label>/<tela>-<dispositivo>-<tema>.png
Não faz parte da suíte `unittest`; serve para comparar antes/depois.
"""
import argparse
import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

VIEWPORTS = {"desktop": (1440, 900), "tablet": (768, 1024), "mobile": (390, 844)}
THEMES = ("light", "dark")

# Telas: (rota, ação JS executada antes da captura ou None)
SCREENS = {
    "login": ("/login", None),
    "register": ("/register", None),
    "reset-password": ("/reset-password", None),
    "home": ("/guest", None),
    "home-catalog": ("/guest", "document.querySelector('#btnOpenCatalog')?.click()"),
    "home-upload": ("/guest", "document.querySelector('#addQuizBtn')?.click()"),
    "home-about": ("/guest", "document.querySelector('#btnOpenAboutModal')?.click()"),
    "home-timer": ("/guest", "document.querySelector('#btnSetTimer')?.click()"),
}

BROWSER_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]
BROWSER_COMMANDS = ["msedge", "microsoft-edge", "google-chrome", "chrome", "chromium"]


def find_browser(explicit: str | None) -> str | None:
    if explicit:
        return explicit if Path(explicit).exists() else shutil.which(explicit)
    for path in BROWSER_CANDIDATES:
        if Path(path).exists():
            return path
    for cmd in BROWSER_COMMANDS:
        found = shutil.which(cmd)
        if found:
            return found
    return None


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class WebSocket:
    """Cliente WebSocket mínimo (RFC 6455), suficiente para o CDP."""

    def __init__(self, url: str):
        parsed = urlparse(url)
        self.sock = socket.create_connection((parsed.hostname, parsed.port), timeout=60)
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            f"GET {parsed.path} HTTP/1.1\r\nHost: {parsed.hostname}:{parsed.port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode())
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("Handshake WebSocket interrompido")
            response += chunk
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise ConnectionError(response.split(b"\r\n", 1)[0].decode(errors="replace"))
        self.buffer = response.split(b"\r\n\r\n", 1)[1]

    def _read(self, n: int) -> bytes:
        while len(self.buffer) < n:
            chunk = self.sock.recv(1 << 20)
            if not chunk:
                raise ConnectionError("Conexão WebSocket encerrada")
            self.buffer += chunk
        data, self.buffer = self.buffer[:n], self.buffer[n:]
        return data

    def send(self, text: str) -> None:
        payload = text.encode()
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 1 << 16:
            header.append(0x80 | 126)
            header += struct.pack(">H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", length)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def recv(self) -> str:
        message = b""
        while True:
            b1, b2 = self._read(2)
            opcode = b1 & 0x0F
            length = b2 & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(length)
            if opcode == 0x8:
                raise ConnectionError("WebSocket fechado pelo navegador")
            if opcode == 0x9:  # ping: ignorado (o CDP não exige pong)
                continue
            message += payload
            if b1 & 0x80:
                return message.decode()

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class Browser:
    def __init__(self, executable: str):
        self.port = free_port()
        self.profile = tempfile.mkdtemp(prefix="quiz-baseline-")
        self.proc = subprocess.Popen(
            [
                executable,
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                "--no-first-run",
                "--no-default-browser-check",
                f"--remote-debugging-port={self.port}",
                f"--user-data-dir={self.profile}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.ws = WebSocket(self._page_ws_url())
        self.next_id = 0

    def _page_ws_url(self) -> str:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/list", timeout=2) as resp:
                    targets = json.load(resp)
                for target in targets:
                    if target.get("type") == "page":
                        return target["webSocketDebuggerUrl"]
            except OSError:
                pass
            time.sleep(0.3)
        raise RuntimeError("O navegador não abriu a porta de depuração a tempo")

    def call(self, method: str, **params):
        self.next_id += 1
        msg_id = self.next_id
        self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params}))
        while True:
            data = json.loads(self.ws.recv())
            if data.get("id") == msg_id:
                if "error" in data:
                    raise RuntimeError(f"{method}: {data['error']}")
                return data.get("result", {})

    def evaluate(self, expression: str, await_promise: bool = False):
        result = self.call("Runtime.evaluate", expression=expression,
                           awaitPromise=await_promise, returnByValue=True)
        return result.get("result", {}).get("value")

    def goto(self, url: str) -> None:
        self.call("Page.navigate", url=url)
        time.sleep(0.2)
        deadline = time.time() + 20
        while time.time() < deadline:
            if self.evaluate("document.readyState") == "complete":
                break
            time.sleep(0.2)
        self.evaluate("document.fonts ? document.fonts.ready.then(() => true) : true", await_promise=True)
        time.sleep(0.8)  # dados assíncronos (lista de quizzes, sessão)

    def close(self) -> None:
        try:
            self.call("Browser.close")
        except Exception:
            pass
        self.ws.close()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.profile, ignore_errors=True)


def capture(browser: Browser, out_file: Path, width: int, height: int, full_page: bool = True) -> None:
    if not full_page:
        # Modais usam overlay fixo: capturar além da viewport só mostraria a página por baixo
        shot = browser.call("Page.captureScreenshot", format="png")
        out_file.write_bytes(base64.b64decode(shot["data"]))
        return
    full_height = browser.evaluate(
        "Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0)"
    ) or height
    full_height = max(height, min(int(full_height), 12000))
    shot = browser.call(
        "Page.captureScreenshot",
        format="png",
        captureBeyondViewport=True,
        clip={"x": 0, "y": 0, "width": width, "height": full_height, "scale": 1},
    )
    out_file.write_bytes(base64.b64decode(shot["data"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--label", default="before")
    parser.add_argument("--out", default="design-baseline")
    parser.add_argument("--browser", help="Caminho do msedge/chrome (detectado automaticamente)")
    parser.add_argument("--only", help="Captura só as telas informadas, separadas por vírgula")
    args = parser.parse_args()

    executable = find_browser(args.browser)
    if not executable:
        print("Edge/Chrome não encontrado. Informe com --browser <caminho>.", file=sys.stderr)
        return 1

    screens = SCREENS
    if args.only:
        wanted = {name.strip() for name in args.only.split(",")}
        screens = {k: v for k, v in SCREENS.items() if k in wanted}

    out_dir = Path(args.out) / args.label
    out_dir.mkdir(parents=True, exist_ok=True)
    base = args.base_url.rstrip("/")
    failures = 0

    browser = Browser(executable)
    try:
        browser.call("Page.enable")
        browser.call("Runtime.enable")
        for theme in THEMES:
            browser.call("Emulation.setEmulatedMedia", features=[
                {"name": "prefers-color-scheme", "value": theme},
                {"name": "prefers-reduced-motion", "value": "reduce"},
            ])
            for vp_name, (width, height) in VIEWPORTS.items():
                browser.call("Emulation.setDeviceMetricsOverride", width=width, height=height,
                             deviceScaleFactor=1, mobile=width < 600)
                browser.call("Emulation.setTouchEmulationEnabled", enabled=width < 600)
                for screen, (path, action) in screens.items():
                    out_file = out_dir / f"{screen}-{vp_name}-{theme}.png"
                    try:
                        if path == "/guest":
                            # Entra no modo convidado do mesmo jeito que o botão da tela de login
                            browser.goto(base + "/login")
                            browser.evaluate("sessionStorage.setItem('quiz_guest_mode', 'true')")
                        browser.goto(base + path)
                        if path == "/guest":
                            # Espera a lista de quizzes e as questões carregarem
                            deadline = time.time() + 10
                            while time.time() < deadline and not browser.evaluate(
                                "document.querySelectorAll('#quiz .question').length > 0"
                            ):
                                time.sleep(0.3)
                        if action:
                            browser.evaluate(action)
                            time.sleep(0.6)
                        capture(browser, out_file, width, height, full_page=action is None)
                        print("ok   ", out_file)
                    except Exception as exc:  # noqa: BLE001 - registra e segue para a próxima tela
                        failures += 1
                        print("FALHA", out_file, f"({exc})")
    finally:
        browser.close()

    print(f"Navegador: {executable}\nScreenshots em: {os.fspath(out_dir)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
