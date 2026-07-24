# RAG Docs Pipeline

Transforme documentacao Markdown de repositorios GitHub em uma experiencia de busca com IA, respostas diretas e evidencias verificaveis.

O RAG Docs Pipeline foi criado para resolver um problema comum em projetos reais: documentacoes grandes, espalhadas e dificeis de consultar. Em vez de procurar manualmente por arquivos, secoes e commits, o usuario pergunta em linguagem natural e recebe uma resposta apoiada por trechos reais da fonte.

## Visao do Produto

A proposta e simples: conectar um repositorio, indexar seus arquivos Markdown e consultar esse conhecimento com seguranca.

Cada resposta mostra de onde veio a informacao, incluindo caminho do arquivo, commit fixado e trecho original. Isso torna a experiencia mais confiavel do que um chatbot generico, porque a resposta nao fica solta: ela vem acompanhada da prova.

## O Que Ele Entrega

- Consulta inteligente sobre documentacao Markdown.
- Painel administrativo para registrar e sincronizar repositorios GitHub.
- Respostas com citacoes e evidencias auditaveis.
- Busca hibrida combinando vetores e texto.
- Interface publica para perguntas e painel protegido para gerenciar fontes.
- Execucao local com Docker, sem depender de infraestrutura paga.

## Por Que E Diferente

O foco nao e apenas "perguntar para uma IA". O diferencial esta em criar uma base de conhecimento rastreavel, onde cada resposta pode ser conferida na fonte original.

Isso aproxima o projeto de casos reais de uso em empresas: documentacao interna, manuais tecnicos, bases de suporte, guias de produto e repositorios com conhecimento espalhado.

## Como Funciona

1. O administrador registra um repositorio GitHub no painel protegido.
2. O sistema coleta os arquivos Markdown do caminho escolhido.
3. O conteudo e dividido, indexado e salvo em PostgreSQL com pgvector.
4. O usuario faz perguntas pelo frontend publico.
5. A resposta retorna com evidencias, citacoes e links para a fonte.

## Rodando Localmente

```bash
cp .env.example .env
docker compose up --build -d
```

Acesse:

- Aplicacao: `http://localhost:3000`
- Painel de fontes: `http://localhost:3000/admin`
- Segredo local do admin: `local-admin-secret`
- API: `http://localhost:8000/docs`

Fluxo recomendado:

1. Abra `http://localhost:3000/admin`.
2. Desbloqueie com `local-admin-secret`.
3. Registre a URL do repositorio, branch e caminho dos Markdown.
4. Volte para `http://localhost:3000` e consulte a documentacao.

## Stack

- Frontend: Next.js
- Backend: FastAPI
- Banco: PostgreSQL + pgvector
- Migrations: Alembic
- Containerizacao: Docker Compose
- Busca: recuperacao hibrida com evidencias por commit

## Status

Este projeto esta pronto como demo local e portfolio tecnico. Ele demonstra uma arquitetura completa de ingestao, indexacao, recuperacao e consulta com evidencias.

Para virar um SaaS publico multiusuario, ainda seriam necessarios autenticacao, cotas, filas, controle de custos e politicas mais fortes contra abuso. A versao atual foi desenhada para apresentar o produto de forma clara, funcional e verificavel em ambiente local.
