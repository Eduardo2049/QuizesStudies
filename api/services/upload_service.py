"""
Upload Service - Orquestra ingestão de novos quizzes.

Fluxo:
1. Recebe arquivo binário + metadata
2. Extrai texto (TXT/PDF/DOCX)
3. Faz parse das questões
4. Detecta se tem gabarito
5. Se NÃO tem gabarito → chama IA (OpenRouter) para gerar
6. Salva no PostgreSQL
7. Retorna dados do quiz criado
"""
import re
from api.utils.file_parser import (
    extract_text,
    detect_has_answer_key,
    parse_questions_from_text,
    validate_questions,
)
from api.services.ai_service import (
    generate_answer_key,
    apply_ai_answers,
    parse_and_structure_questions_with_ai,
    AIServiceError,
)
from api.utils.config import OPENROUTER_API_KEY, GEMINI_API_KEY
from api.repositories.quiz_repository import QuizRepository
from api.exceptions.quiz_exceptions import QuizAPIException


def _slugify(text: str) -> str:
    """Transforma um nome em slug seguro para usar como `name` no banco."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:120]


class UploadService:
    """Service para processamento e ingesta de novos quizzes"""

    MAX_QUESTIONS = 500
    MAX_UPLOAD_BYTES = 20 * 1024 * 1024        # 20 MB (autenticado)
    MAX_GUEST_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB (convidado)
    ALLOWED_FILE_TYPES = {"txt", "pdf", "docx"}

    def __init__(self, repository: QuizRepository | None = None):
        self.repo = repository or QuizRepository()

    def process_upload(
        self,
        filename: str,
        content: bytes,
        file_type: str,
        created_by: int | None,
        is_public: bool,
        persist: bool = True,
        client_ip: str | None = None,
        num_questions: str | int = "auto",
        context: str = "",
    ) -> dict:
        """
        Processa upload de arquivo e cria quiz no banco.

        Args:
            filename: Nome original do arquivo (ex: 'prova_2024.pdf')
            content: Bytes do arquivo
            file_type: 'txt', 'pdf' ou 'docx'
            created_by: ID do usuário (ou None para guest)
            is_public: Se o quiz deve ser público
            persist: Se deve salvar no banco ou retornar apenas em memória
            client_ip: IP do cliente
            num_questions: Quantidade de questões desejada ('auto' ou 1 a 30)
            context: Diretrizes/foco adicional para adaptação por IA

        Returns:
            dict: {quiz_id, name, label, question_count, ai_generated}

        Raises:
            QuizAPIException: Se parsing falhar ou IA não disponível
        """
        is_guest = created_by is None or not persist

        # 0. Validação de tipo de arquivo e peso
        clean_ext = file_type.lower().lstrip(".")
        if clean_ext not in self.ALLOWED_FILE_TYPES:
            raise QuizAPIException(
                f"Tipo de arquivo não suportado: .{clean_ext}. Use TXT, PDF ou DOCX.",
                400
            )

        limit_bytes = self.MAX_GUEST_UPLOAD_BYTES if is_guest else self.MAX_UPLOAD_BYTES
        if content and len(content) > limit_bytes:
            mb = limit_bytes // (1024 * 1024)
            msg = (
                f"Arquivo excede o limite máximo permitido de {mb} MB para convidados. Faça login para enviar até 20 MB."
                if is_guest else
                f"Arquivo excede o limite máximo permitido de {mb} MB"
            )
            raise QuizAPIException(msg, 413)

        target_qty = None
        if num_questions and str(num_questions).lower() != "auto":
            try:
                target_qty = max(1, min(int(num_questions), 30))
            except (ValueError, TypeError):
                target_qty = None

        # 1. Extrair texto com limites específicos para visitante
        try:
            text = extract_text(content, file_type, is_guest=is_guest)
        except ImportError as e:
            raise QuizAPIException(str(e), 500)
        except Exception as e:
            raise QuizAPIException(f"Erro ao ler o arquivo: {e}", 400)

        if not text.strip():
            raise QuizAPIException("O arquivo está vazio ou não contém texto extraível", 400)

        if len(text) > 1_000_000:
            raise QuizAPIException("Texto extraído excede o limite permitido", 413)

        # 2. Parse das questões (Camada 1: Heurística / Regex Multi-Padrão)
        questions = parse_questions_from_text(text)
        is_valid, error_msg = validate_questions(questions)
        ai_generated = False

        # Camada 2: Fallback para IA se o regex não encontrar questões válidas
        # (ex: TXT sem numeração, texto de estudo/resumo, perguntas livres)
        if not is_valid:
            if created_by is None:
                raise QuizAPIException(
                    "O arquivo requer estruturação por Inteligência Artificial. "
                    "Faça login para utilizar recursos com IA.",
                    401
                )
            has_ai_key = bool(GEMINI_API_KEY or OPENROUTER_API_KEY)
            if has_ai_key:
                try:
                    questions = parse_and_structure_questions_with_ai(
                        text, client_ip=client_ip, num_questions=target_qty, context=context
                    )
                    is_valid, error_msg = validate_questions(questions)
                    if is_valid:
                        ai_generated = True
                except AIServiceError as e:
                    raise QuizAPIException(
                        f"Não foi possível estruturar as questões do arquivo automaticamente com IA: {e}",
                        422
                    )
                except Exception as e:
                    raise QuizAPIException(
                        f"Erro na análise do documento por IA: {e}",
                        422
                    )

            if not is_valid:
                raise QuizAPIException(
                    f"Arquivo com formato não reconhecido: {error_msg}. "
                    "Verifique se o arquivo possui questões e alternativas ou configure a IA (GEMINI_API_KEY / OPENROUTER_API_KEY) para interpretação automática.",
                    400
                )

        # Aplicar corte para a quantidade solicitada se o arquivo tiver mais questões
        if target_qty and len(questions) > target_qty:
            questions = questions[:target_qty]
            for i, q in enumerate(questions, start=1):
                q["id"] = i
                q["question_number"] = i

        if len(questions) > self.MAX_QUESTIONS:
            raise QuizAPIException(
                f"O arquivo excede o limite de {self.MAX_QUESTIONS} questões", 413
            )

        # 3. Detectar gabarito e gerar respostas faltantes se necessário
        questions_without_answers = [
            q for q in questions if q.get("answer") is None
        ]
        if questions_without_answers:
            if created_by is None:
                raise QuizAPIException(
                    "O arquivo não possui gabarito e a resolução por Inteligência Artificial requer login. "
                    "Faça login para utilizar recursos com IA.",
                    401
                )
            try:
                ai_answers = generate_answer_key(questions_without_answers, client_ip=client_ip)
                questions = apply_ai_answers(questions, ai_answers)
                ai_generated = True
            except AIServiceError as e:
                raise QuizAPIException(
                    f"Gabarito não encontrado no arquivo e a IA não pôde gerá-lo: {e}",
                    422
                )

        # Verificar que todas as questões têm resposta
        missing = [q["id"] for q in questions if q.get("answer") is None]
        if missing:
            raise QuizAPIException(
                f"Questões sem gabarito: {missing}. Configure GEMINI_API_KEY ou OPENROUTER_API_KEY para gerar automaticamente.",
                422
            )

        # 5. Preparar o resultado sem persistir quando for um convidado
        stem = re.sub(r"\.[^.]+$", "", filename)  # remover extensão
        label = stem.replace("_", " ").replace("-", " ").title()
        name = _slugify(stem)

        if not persist:
            return {
                "quiz_id": None,
                "name": name,
                "label": label,
                "question_count": len(questions),
                "ai_generated": ai_generated,
                "local_only": True,
                "questions": questions,
                "message": f"Quiz '{label}' carregado somente neste dispositivo",
            }

        # Garantir nome único
        base_name = name
        counter = 1
        while self.repo.name_exists(name):
            name = f"{base_name}-{counter}"
            counter += 1

        # Normalizar question_number
        for i, q in enumerate(questions, start=1):
            q["question_number"] = q.get("id", i)

        # 6. Salvar no banco
        quiz = self.repo.save_quiz(
            name=name,
            label=label,
            questions=questions,
            original_filename=filename,
            file_type=file_type.lstrip("."),
            ai_generated=ai_generated,
            created_by=created_by,
            is_public=is_public,
        )

        return {
            "quiz_id": quiz["id"],
            "name": quiz["name"],
            "label": quiz["label"],
            "question_count": len(questions),
            "ai_generated": ai_generated,
            "message": (
                f"Quiz '{label}' criado com {len(questions)} questões"
                + (" (gabarito gerado por IA)" if ai_generated else "")
            ),
        }
