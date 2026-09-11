"""
Teste automatizado End-to-End para autenticação e controle de acesso
"""
import subprocess
import sys
import time
import json
import os
import urllib.request
import urllib.error

def run_test():
    env = os.environ.copy()
    env["PORT"] = "8005"
    proc = subprocess.Popen(
        [sys.executable, "-u", "quiz_api.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    time.sleep(2)

    base = "http://localhost:8005"

    def do_req(path, data=None, headers=None, method=None):
        h = headers or {}
        body = None
        if data is not None:
            if isinstance(data, dict):
                body = json.dumps(data).encode("utf-8")
                h["Content-Type"] = "application/json"
            else:
                body = data
        req = urllib.request.Request(f"{base}{path}", data=body, headers=h, method=method)
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    try:
        # 1. Login com senha errada
        st, data = do_req("/api/auth/login", {"username": "admin", "password": "wrongpassword"})
        assert st == 401, f"Esperado 401, obtido {st}"
        print("[PASS] 1. Login com senha errada rejeitado (401)")

        # 2. Login com admin correto
        admin_password = os.environ.get("ADMIN_PASSWORD")
        assert admin_password, "ADMIN_PASSWORD deve estar configurada para o teste"
        st, data = do_req("/api/auth/login", {"username": "admin", "password": admin_password})
        assert st == 200, f"Esperado 200, obtido {st}"
        admin_token = data["data"]["token"]
        assert admin_token, "Token não retornado"
        print("[PASS] 2. Login de admin realizado com sucesso (200)")

        # 3. GET /api/auth/me com token
        st, data = do_req("/api/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
        assert st == 200 and data["data"]["user"]["username"] == "admin", "Erro ao validar /me"
        print("[PASS] 3. /api/auth/me validou sessão com sucesso")

        # 4. Upload sem token (deve ser 401)
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
        upload_body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="teste_prova.txt"\r\n'
            "Content-Type: text/plain\r\n\r\n"
            "**1.** Questão teste de raciocínio?\n"
            "a) Opção A\n"
            "b) Opção B\n\n"
            "# Gabarito\n"
            "1. a) Opção A\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        h_upload = {"Content-Type": f"multipart/form-data; boundary={boundary}"}

        st, data = do_req("/api/upload", data=upload_body, headers=h_upload)
        assert st == 401, f"Esperado 401 sem token, obtido {st}"
        print("[PASS] 4. Upload bloqueado sem token (401 Unauthorized)")

        # 5. Registro de estudante
        st, data = do_req("/api/auth/register", {
            "username": "aluno_teste",
            "email": "aluno_teste@escola.com",
            "password": "senha_estudante_123"
        })
        # Se já existe de rodada anterior ou criou novo:
        if st == 409:
            st, data = do_req("/api/auth/login", {
                "username": "aluno_teste",
                "password": "senha_estudante_123"
            })
            student_token = data["data"]["token"]
        else:
            assert st == 201, f"Esperado 201, obtido {st}: {data}"
            st, data = do_req("/api/auth/login", {
                "username": "aluno_teste",
                "password": "senha_estudante_123"
            })
            student_token = data["data"]["token"]
        print("[PASS] 5. Autenticação de estudante verificada")

        # 6. Upload com token de estudante (deve ser 403 Forbidden)
        h_student = dict(h_upload)
        h_student["Authorization"] = f"Bearer {student_token}"
        st, data = do_req("/api/upload", data=upload_body, headers=h_student)
        assert st == 403, f"Esperado 403 para estudante, obtido {st}"
        print("[PASS] 6. Upload bloqueado para estudante (403 Forbidden)")

        # 7. Upload com token de admin (deve ser 201 Created)
        h_admin = dict(h_upload)
        h_admin["Authorization"] = f"Bearer {admin_token}"
        st, data = do_req("/api/upload", data=upload_body, headers=h_admin)
        assert st == 201, f"Esperado 201 para admin, obtido {st}: {data}"
        print("[PASS] 7. Upload autorizado com sucesso para admin (201 Created)")

        # 8. Logout
        st, data = do_req("/api/auth/logout", headers={"Authorization": f"Bearer {admin_token}"}, method="POST")
        assert st == 200, f"Esperado 200 no logout, obtido {st}"
        st, data = do_req("/api/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
        assert st == 401, f"Esperado 401 após logout, obtido {st}"
        print("[PASS] 8. Logout e invalidação de sessão verificados com sucesso")

        print("\n>>> TODOS OS 8 TESTES DE SEGURANCA E AUTENTICACAO PASSARAM COM SUCESSO! <<<")
    finally:
        proc.terminate()

if __name__ == "__main__":
    run_test()
