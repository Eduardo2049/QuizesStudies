# Instruções para o Copilot (Acely)

Este repositório é o **Acely** (acely.com.br), antes chamado Quiz Study.

1. As regras do projeto, o mapa de arquivos e as proibições estão em [`AGENTS.md`](../AGENTS.md). Leia antes de qualquer mudança.
2. O trabalho em andamento está em [`docs/PLANO_SAAS.md`](../docs/PLANO_SAAS.md) (as fases de IA já foram concluídas; o funcionamento está em [`docs/ARQUITETURA.md`](../docs/ARQUITETURA.md)): uma branch `feature/*` e um PR para a `develop` por fase.
3. Antes de abrir PR: `python -m unittest discover tests` com `ADMIN_PASSWORD` definido.
