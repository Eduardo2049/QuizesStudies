"""
Acervo de simulados prontos para os temas de exemplo da interface (.topic-chip).

Temas de exemplo prontos (docs/ARQUITETURA.md, seção da IA): clicar em um tema de exemplo e gerar com os parâmetros
padrão (até 5 questões, nível Médio, sem instruções extras, pt-BR) responde
instantaneamente sem chamar a IA nem descontar cota (cached=True).
"""
from __future__ import annotations

import copy
import re
import unicodedata


def _norm(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    ascii_like = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^a-z0-9\s]", " ", ascii_like.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


_PRESET_QUIZZES: list[dict] = [
    {
        "aliases": ("Juros simples e compostos", "Juros compostos"),
        "title": "Juros Simples e Compostos",
        "topic": "Juros simples e compostos",
        "questions": [
            {
                "id": 1,
                "question_number": 1,
                "section": "Juros Simples",
                "context": "",
                "question": "Um capital de R$ 2.000,00 é aplicado a juros simples à taxa de 2% ao mês durante 5 meses. Qual é o valor total dos juros produzidos?",
                "options": ["R$ 150,00", "R$ 200,00", "R$ 220,00", "R$ 250,00"],
                "answer": 1,
                "explanation": "Nos juros simples, J = C × i × t. Assim, J = 2000 × 0,02 × 5 = R$ 200,00.",
                "verified": True,
            },
            {
                "id": 2,
                "question_number": 2,
                "section": "Juros Compostos",
                "context": "",
                "question": "Um investimento de R$ 1.000,00 rende juros compostos de 10% ao ano. Qual será o montante ao final de 2 anos?",
                "options": ["R$ 1.200,00", "R$ 1.210,00", "R$ 1.220,00", "R$ 1.250,00"],
                "answer": 1,
                "explanation": "Nos juros compostos, M = C × (1 + i)^t. Logo, M = 1000 × (1,10)^2 = 1000 × 1,21 = R$ 1.210,00.",
                "verified": True,
            },
            {
                "id": 3,
                "question_number": 3,
                "section": "Comparação de Regimes",
                "context": "",
                "question": "Em relação a um mesmo capital, taxa positiva e prazo superior a 1 período, qual afirmação compara corretamente juros simples e juros compostos?",
                "options": [
                    "Os juros simples sempre geram montante maior que os compostos.",
                    "Os dois regimes produzem o mesmo montante em qualquer prazo.",
                    "Os juros compostos geram montante maior por incidirem sobre o montante acumulado.",
                    "Os juros compostos só superam os simples quando a taxa é maior que 50%.",
                ],
                "answer": 2,
                "explanation": "Para prazos maiores que 1 período e taxa positiva, os juros compostos capitalizam juros sobre juros, superando o crescimento linear dos juros simples.",
                "verified": True,
            },
            {
                "id": 4,
                "question_number": 4,
                "section": "Taxa e Prazo",
                "context": "",
                "question": "Qual é o montante obtido ao aplicar R$ 500,00 a juros simples de 3% ao mês durante 4 meses?",
                "options": ["R$ 540,00", "R$ 550,00", "R$ 560,00", "R$ 562,75"],
                "answer": 2,
                "explanation": "Os juros são J = 500 × 0,03 × 4 = R$ 60,00. Somando ao capital inicial, o montante é M = 500 + 60 = R$ 560,00.",
                "verified": True,
            },
            {
                "id": 5,
                "question_number": 5,
                "section": "Juros Compostos",
                "context": "",
                "question": "Um empréstimo de R$ 400,00 foi contratado a juros compostos de 5% ao mês. Quanto será pago de juros apenas no segundo mês?",
                "options": ["R$ 20,00", "R$ 21,00", "R$ 40,00", "R$ 41,00"],
                "answer": 1,
                "explanation": "No 1º mês, os juros são 5% de 400 = R$ 20,00 (montante R$ 420,00). No 2º mês, os juros incidem sobre R$ 420,00: 5% × 420 = R$ 21,00.",
                "verified": True,
            },
        ],
    },
    {
        "aliases": ("Uso da crase na língua portuguesa", "Crase"),
        "title": "Uso da Crase na Língua Portuguesa",
        "topic": "Uso da crase na língua portuguesa",
        "questions": [
            {
                "id": 1,
                "question_number": 1,
                "section": "Regra Geral",
                "context": "",
                "question": "Em qual alternativa o emprego do acento indicativo de crase está correto?",
                "options": [
                    "O aluno começou à estudar cedo para a prova.",
                    "Entregamos o relatório à diretora da escola.",
                    "Viajaremos à cavalo pela trilha da serra.",
                    "Ficamos frente à frente durante a reunião.",
                ],
                "answer": 1,
                "explanation": "O verbo 'entregar' exige preposição 'a' e 'diretora' admite artigo definido 'a', formando a crase ('à diretora'). Não ocorre crase antes de verbo, palavra masculina ou palavras repetidas.",
                "verified": True,
            },
            {
                "id": 2,
                "question_number": 2,
                "section": "Locuções",
                "context": "",
                "question": "Assinale a frase em que a crase é obrigatória por se tratar de locução adverbial feminina:",
                "options": [
                    "A reunião foi marcada as pressas pela equipe.",
                    "Ele prefere escrever a lápis no caderno.",
                    "O pagamento deve ser feito a prazo.",
                    "Caminhamos a pé até a estação central.",
                ],
                "answer": 0,
                "explanation": "'Às pressas' é uma locução adverbial feminina e exige acento grave. Já 'a lápis', 'a prazo' e 'a pé' têm núcleos masculinos.",
                "verified": True,
            },
            {
                "id": 3,
                "question_number": 3,
                "section": "Indicação de Horas",
                "context": "",
                "question": "Qual frase emprega corretamente a crase na indicação de horas?",
                "options": [
                    "O simulado começa às 14 horas em ponto.",
                    "A aula terminou após às 18 horas.",
                    "Ficaremos estudando daqui à duas horas.",
                    "O evento vai de 9h às 12h sem intervalo.",
                ],
                "answer": 0,
                "explanation": "Antes de hora exata determinada ('às 14 horas'), usa-se crase. Após preposições como 'após', não ocorre crase; em 'de 9h a 12h' sem artigo antes de '9h', mantém-se paralelismo sem crase.",
                "verified": True,
            },
            {
                "id": 4,
                "question_number": 4,
                "section": "Casos Facultativos",
                "context": "",
                "question": "Em qual das opções o uso da crase é facultativo segundo a norma-padrão?",
                "options": [
                    "Fui à farmácia comprar remédios.",
                    "Referi-me àquela questão difícil.",
                    "Entreguei o convite à minha irmã.",
                    "Chegamos à cidade ao anoitecer.",
                ],
                "answer": 2,
                "explanation": "Antes de pronome possessivo feminino no singular ('minha irmã'), o artigo definido é opcional; por isso, a crase é facultativa.",
                "verified": True,
            },
            {
                "id": 5,
                "question_number": 5,
                "section": "Nomes de Lugares",
                "context": "",
                "question": "Aplicando a regra prática 'volto da / volto de', em qual frase a crase está empregada corretamente?",
                "options": [
                    "No próximo feriado, viajaremos à Curitiba.",
                    "Todos os anos ela retorna à Bahia.",
                    "O navio chegou à Portugal na madrugada.",
                    "A delegação embarcou rumo à Brasília.",
                ],
                "answer": 1,
                "explanation": "Quem volta 'da' Bahia usa crase ('à Bahia'). Curitiba, Portugal e Brasília não exigem artigo ('volto de'), portanto não levam crase sem especificador.",
                "verified": True,
            },
        ],
    },
    {
        "aliases": ("Lógica proposicional e tabela-verdade", "Tabela-verdade"),
        "title": "Lógica Proposicional e Tabela-Verdade",
        "topic": "Lógica proposicional e tabela-verdade",
        "questions": [
            {
                "id": 1,
                "question_number": 1,
                "section": "Condicional",
                "context": "",
                "question": "Na lógica proposicional, em qual única situação a proposição condicional 'P → Q' é falsa?",
                "options": [
                    "Quando P é falsa e Q é falsa.",
                    "Quando P é verdadeira e Q é falsa.",
                    "Quando P é falsa e Q é verdadeira.",
                    "Quando P e Q são ambas verdadeiras.",
                ],
                "answer": 1,
                "explanation": "A condicional 'P → Q' só assume valor lógico falso quando o antecedente (P) é verdadeiro e o consequente (Q) é falso.",
                "verified": True,
            },
            {
                "id": 2,
                "question_number": 2,
                "section": "Leis de De Morgan",
                "context": "",
                "question": "Qual proposição é logicamente equivalente à negação de 'P ∧ Q' (isto é, ¬(P ∧ Q))?",
                "options": ["¬P ∧ ¬Q", "¬P ∨ ¬Q", "P → ¬Q", "¬P ↔ ¬Q"],
                "answer": 1,
                "explanation": "Pela Lei de De Morgan, a negação de uma conjunção '¬(P ∧ Q)' equivale à disjunção das negações: '¬P ∨ ¬Q'.",
                "verified": True,
            },
            {
                "id": 3,
                "question_number": 3,
                "section": "Tabela-Verdade",
                "context": "",
                "question": "Quantas linhas possui a tabela-verdade de uma proposição composta formada por 4 proposições simples distintas?",
                "options": ["8 linhas", "12 linhas", "16 linhas", "32 linhas"],
                "answer": 2,
                "explanation": "O número de linhas da tabela-verdade é dado por 2^n, onde n é o número de proposições simples. Para n = 4, temos 2^4 = 16 linhas.",
                "verified": True,
            },
            {
                "id": 4,
                "question_number": 4,
                "section": "Equivalências Lógicas",
                "context": "",
                "question": "Qual proposição corresponde à contrapositiva equivalente de 'Se estudo, então passo' (P → Q)?",
                "options": [
                    "Se passo, então estudo (Q → P).",
                    "Se não estudo, então não passo (¬P → ¬Q).",
                    "Se não passo, então não estudo (¬Q → ¬P).",
                    "Estudo e não passo (P ∧ ¬Q).",
                ],
                "answer": 2,
                "explanation": "A contrapositiva de 'P → Q' inverte e nega ambos os termos ('¬Q → ¬P'), preservando exatamente a mesma tabela-verdade.",
                "verified": True,
            },
            {
                "id": 5,
                "question_number": 5,
                "section": "Bicondicional",
                "context": "",
                "question": "Quando a proposição bicondicional 'P ↔ Q' assume valor lógico verdadeiro?",
                "options": [
                    "Apenas quando P e Q são ambas verdadeiras.",
                    "Quando P e Q possuem o mesmo valor lógico (ambas V ou ambas F).",
                    "Quando P e Q possuem valores lógicos opostos.",
                    "Sempre que pelo menos uma das proposições for verdadeira.",
                ],
                "answer": 1,
                "explanation": "A bicondicional 'P ↔ Q' é verdadeira sempre que P e Q têm valores lógicos idênticos (V e V, ou F e F).",
                "verified": True,
            },
        ],
    },
    {
        "aliases": (
            "Direito constitucional: direitos e garantias fundamentais",
            "Direitos fundamentais",
        ),
        "title": "Direito Constitucional: Direitos e Garantias Fundamentais",
        "topic": "Direito constitucional: direitos e garantias fundamentais",
        "questions": [
            {
                "id": 1,
                "question_number": 1,
                "section": "Artigo 5º da CF/88",
                "context": "",
                "question": "Segundo o artigo 5º da Constituição Federal de 1988, sobre a inviolabilidade do domicílio, em qual situação é permitido entrar na casa sem consentimento do morador durante a noite?",
                "options": [
                    "Mediante determinação judicial.",
                    "Em caso de flagrante delito, desastre ou para prestar socorro.",
                    "Por ordem administrativa da autoridade policial.",
                    "Em qualquer investigação criminal em andamento.",
                ],
                "answer": 1,
                "explanation": "Conforme o art. 5º, XI da CF/88, durante a noite só é permitido ingressar sem consentimento em caso de flagrante delito, desastre ou para prestar socorro; ordem judicial só autoriza o ingresso durante o dia.",
                "verified": True,
            },
            {
                "id": 2,
                "question_number": 2,
                "section": "Remédios Constitucionais",
                "context": "",
                "question": "Qual remédio constitucional é cabível para proteger direito líquido e certo não amparado por habeas corpus ou habeas data?",
                "options": [
                    "Ação popular",
                    "Mandado de segurança",
                    "Mandado de injunção",
                    "Reclamação constitucional",
                ],
                "answer": 1,
                "explanation": "Nos termos do art. 5º, LXIX da CF/88, concede-se mandado de segurança para proteger direito líquido e certo não amparado por habeas corpus ou habeas data.",
                "verified": True,
            },
            {
                "id": 3,
                "question_number": 3,
                "section": "Remédios Constitucionais",
                "context": "",
                "question": "O habeas data é o remédio constitucional destinado principalmente a:",
                "options": [
                    "Garantir a liberdade de locomoção contra ilegalidade ou abuso de poder.",
                    "Assegurar o conhecimento ou a retificação de informações pessoais em bancos de dados públicos.",
                    "Anular ato lesivo ao patrimônio público ou à moralidade administrativa.",
                    "Suprir a falta de norma regulamentadora que inviabilize o exercício de direitos.",
                ],
                "answer": 1,
                "explanation": "Segundo o art. 5º, LXXII da CF/88, o habeas data assegura o conhecimento e a retificação de dados relativos à pessoa do impetrante em registros ou bancos de dados públicos ou de caráter público.",
                "verified": True,
            },
            {
                "id": 4,
                "question_number": 4,
                "section": "Aplicabilidade",
                "context": "",
                "question": "De acordo com o § 1º do artigo 5º da Constituição Federal, as normas definidoras dos direitos e garantias fundamentais têm:",
                "options": [
                    "Aplicação condicionada à aprovação de lei complementar.",
                    "Aplicação imediata.",
                    "Eficácia limitada até regulamentação pelo Poder Executivo.",
                    "Validade restrita aos brasileiros natos.",
                ],
                "answer": 1,
                "explanation": "O art. 5º, § 1º da CF/88 estabelece expressamente que as normas definidoras dos direitos e garantias fundamentais têm aplicação imediata.",
                "verified": True,
            },
            {
                "id": 5,
                "question_number": 5,
                "section": "Cláusulas Pétreas",
                "context": "",
                "question": "Em relação às emendas constitucionais (art. 60, § 4º da CF/88), os direitos e garantias individuais:",
                "options": [
                    "Podem ser abolidos por emenda aprovada por maioria absoluta.",
                    "Constituem cláusula pétrea, não podendo ser objeto de proposta tendente a aboli-los.",
                    "Podem ser suspensos definitivamente por decreto legislativo.",
                    "Só são protegidos durante o mandato do presidente eleito.",
                ],
                "answer": 1,
                "explanation": "O art. 60, § 4º, IV da CF/88 protege os direitos e garantias individuais como cláusula pétrea, vedando proposta de emenda tendente a aboli-los.",
                "verified": True,
            },
        ],
    },
]

_PRESETS_BY_KEY: dict[str, dict] = {
    _norm(alias): preset
    for preset in _PRESET_QUIZZES
    for alias in preset["aliases"]
}


def get_preset_quiz(
    topic: str,
    qty: int = 5,
    difficulty: str = "Médio",
    context: str = "",
    language: str = "pt-BR",
) -> dict | None:
    """Retorna um simulado pronto do acervo para temas de exemplo sem chamar a IA."""
    if context.strip() or difficulty != "Médio" or language != "pt-BR":
        return None
    preset = _PRESETS_BY_KEY.get(_norm(topic))
    if not preset:
        return None
    all_questions = preset["questions"]
    if qty < 1 or qty > len(all_questions):
        return None
    selected = copy.deepcopy(all_questions[:qty])
    for idx, q in enumerate(selected, start=1):
        q["id"] = idx
        q["question_number"] = idx
    return {
        "title": preset["title"],
        "topic": preset["topic"],
        "questions": selected,
        "usage": {},
        "model": "preset",
        "provider": "Acely Preset",
        "verified_count": len(selected),
        "cached": True,
        "sample_preset": True,
    }
