"""DTOs — estruturas de dados trafegadas entre camadas"""
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class QuestionDTO:
    id: int
    section: str
    question: str
    options: List[str]
    context: str = ""
    answer: Optional[int] = None       # nunca exposto ao cliente
    explanation: Optional[str] = None  # nunca exposto ao cliente


@dataclass
class QuizDTO:
    title: str
    source: str
    questions: List[QuestionDTO]


@dataclass
class GradeResultDTO:
    score: int
    total: int
    percentage: int
    results: List[dict]
    wrong_ids: List[int] = field(default_factory=list)
    attempt_id: Optional[int] = None
