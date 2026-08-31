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
    def find_all_sources() -> list[Path]:
        """
        Encontra todos os quizzes disponíveis.
        Busca .md e arquivos "\\d+ test"
        
        Returns:
            list[Path]: Lista de caminhos dos quizzes
        """
        sources = list(ROOT.glob("*.md"))
        sources.extend(
            path for path in ROOT.iterdir()
            if path.is_file() and re.match(r"^\d+\s+test$", path.name, re.IGNORECASE)
        )
        
        return sorted(
            {path.resolve(): path for path in sources 
             if path.name.lower() != "readme.md"}.values(),
            key=lambda path: path.name.lower(),
        )

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
        2. Arquivo numerado mais alto (ex: "3 test")
        3. Primeiro .md
        4. Padrão: "1 test"
        
        Returns:
            Path: Caminho do arquivo
        """
        # 1. Variável de ambiente
        configured = os.getenv("QUIZ_MARKDOWN")
        if configured:
            path = Path(configured)
            if path.exists():
                return path

        # 2. Procurar arquivos
        sources = QuizRepository.find_all_sources()
        if sources:
            # Priorizar numerados como "3 test", "2 test"
            numbered = [
                p for p in sources 
                if re.match(r"^\d+\s+test$", p.name, re.IGNORECASE)
            ]
            if numbered:
                return max(numbered, key=lambda p: int(p.name.split()[0]))
            return sources[0]

        # 3. Padrão (pode não existir)
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
        except FileNotFoundError:
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
