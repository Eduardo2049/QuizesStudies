"""
DTOs (Data Transfer Objects) - Padrão Spring
Definem a estrutura de dados trafegados na API
"""
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class QuestionDTO:
    """DTO para uma questão"""
    id: int
    section: str
    question: str
    options: List[str]
    context: str = ""
    answer: Optional[int] = None      # Apenas no backend
    explanation: Optional[str] = None  # Apenas no backend


@dataclass
class QuizDTO:
    """DTO para um quiz completo"""
    title: str
    source: str
    questions: List[QuestionDTO]


@dataclass
class SubmitAnswersDTO:
    """DTO para submissão de respostas"""
    answers: dict  # {question_id: option_index}
    source: Optional[str] = None


@dataclass
class GradeResultDTO:
    """DTO para resultado da correção"""
    score: int
    total: int
    percentage: int
    results: List[dict]


@dataclass
class QuizListDTO:
    """DTO para lista de quizzes"""
    quizzes: List[dict]


@dataclass
class QuizFileDTO:
    """DTO para arquivo de quiz"""
    name: str
    label: str


@dataclass
class UploadResponseDTO:
    """DTO para resposta de upload"""
    success: bool
    message: str
    filename: Optional[str] = None
    error: Optional[str] = None
