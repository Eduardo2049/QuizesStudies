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
from api.services.ai_service import generate_answer_key, apply_ai_answers, AIServiceError
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

    def __init__(self, repository: QuizRepository = None):
        self.repo = repository or QuizRepository()

    def process_upload(
        self,
        filename: str,
        content: bytes,
        file_type: str,
        created_by: int,
        is_public: bool,
        persist: bool = True,
    ) -> dict:
        """
        Processa upload de arquivo e cria quiz no banco.

        Args:
            filename: Nome original do arquivo (ex: 'prova_2024.pdf')
            content: Bytes do arquivo
            file_type: 'txt', 'pdf' ou 'docx'

        Returns:
            dict: {quiz_id, name, label, question_count, ai_generated}

        Raises:
            QuizAPIException: Se parsing falhar ou IA não disponível
        """
        # 1. Extrair texto
        try:
            text = extract_text(content, file_type)
        except ImportError as e:
            raise QuizAPIException(str(e), 500)
        except Exception as e:
            raise QuizAPIException(f"Erro ao ler o arquivo: {e}", 400)

        if not text.strip():
            raise QuizAPIException("O arquivo está vazio ou não contém texto extraível", 400)

        if len(text) > 1_000_000:
            raise QuizAPIException("Texto extraído excede o limite permitido", 413)

        # 2. Parse das questões
        questions = parse_questions_from_text(text)

        if len(questions) > self.MAX_QUESTIONS:
            raise QuizAPIException(
                f"O arquivo excede o limite de {self.MAX_QUESTIONS} questões", 413
            )

        is_valid, error_msg = validate_questions(questions)
        if not is_valid:
            raise QuizAPIException(f"Arquivo inválido: {error_msg}", 400)

        # 3. Detectar gabarito
        has_answer_key = detect_has_answer_key(text)
        ai_generated = False

        # 4. Gerar gabarito via IA se necessário
        if not has_answer_key:
            questions_without_answers = [
                q for q in questions if q.get("answer") is None
            ]
            if questions_without_answers:
                try:
                    ai_answers = generate_answer_key(questions_without_answers)
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
                f"Questões sem gabarito: {missing}. Configure OPENROUTER_API_KEY para gerar automaticamente.",
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
