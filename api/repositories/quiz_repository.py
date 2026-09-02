"""
Repositories - Padrão Spring @Repository
Camada de acesso a dados (arquivos Markdown)
"""
from pathlib import Path
import re
import os

from api.utils.config import ROOT
from api.exceptions.quiz_exceptions import QuizNotFound, FileNotFoundError


class QuizRepository:
    """Repository para operações com arquivos de quiz"""

    @staticmethod
    def is_valid_quiz_file(path: Path) -> bool:
        """Verifica se o arquivo é um questionário válido"""
        if not path.is_file():
            return False
        if path.name.lower() in ("readme.md", "license.md", "changelog.md"):
            return False
        if re.match(r"^\d+\s+test(\.md)?$", path.name, re.IGNORECASE):
            return True
        if path.suffix.lower() == ".md":
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                return "# Gabarito" in content and "**1.**" in content
            except Exception:
                return False
        return False

    @staticmethod
    def find_all_sources() -> list[Path]:
        """
        Encontra todos os quizzes disponíveis.
        Busca .md válidos e arquivos '\\d+ test'
        
        Returns:
            list[Path]: Lista de caminhos dos quizzes ordenados
        """
        sources = set()
        if ROOT.exists():
            for path in ROOT.iterdir():
                if QuizRepository.is_valid_quiz_file(path):
                    sources.add(path.resolve())

        def sort_key(p: Path):
            match = re.match(r"^(\d+)", p.name)
            if match:
                return (0, int(match.group(1)), p.name.lower())
            return (1, 0, p.name.lower())

        return sorted([Path(p) for p in sources], key=sort_key)

    @staticmethod
    def find_by_name(source_name: str) -> Path:
        """
        Encontra um quiz pelo nome.
        
        Args:
            source_name (str): Nome do arquivo
            
        Returns:
            Path: Caminho do arquivo
            
        Raises:
            QuizNotFound: Se não encontrar
        """
        for path in QuizRepository.find_all_sources():
            if path.name == source_name:
                return path
        raise QuizNotFound(source_name)

    @staticmethod
    def find_default() -> Path:
        """
        Encontra o quiz padrão a usar.
        
        Prioridade:
        1. QUIZ_MARKDOWN env var
        2. Primeiro arquivo disponível
        3. Padrão: "1 test"
        
        Returns:
            Path: Caminho do arquivo
        """
        # 1. Variável de ambiente
        configured = os.getenv("QUIZ_MARKDOWN")
        if configured:
            path = Path(configured)
            if path.exists():
                return path

        # 2. Procurar arquivos disponíveis
        sources = QuizRepository.find_all_sources()
        if sources:
            return sources[0]

        # 3. Padrão fallback
        return ROOT / "1 test"

    @staticmethod
    def read_file(path: Path) -> str:
        """
        Lê arquivo Markdown.
        
        Args:
            path (Path): Caminho do arquivo
            
        Returns:
            str: Conteúdo do arquivo
            
        Raises:
            FileNotFoundError: Se arquivo não existe
        """
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            raise FileNotFoundError(str(path))

    @staticmethod
    def save_file(path: Path, content: str) -> None:
        """
        Salva arquivo Markdown.
        
        Args:
            path (Path): Caminho do arquivo
            content (str): Conteúdo a salvar
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
