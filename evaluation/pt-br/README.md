# Fonte de avaliacao PT-BR

## Fonte aprovada

- Repositorio: https://github.com/fastapi/fastapi
- Branch: `master`
- Path: `docs/pt/docs`
- Idioma: `pt-BR`
- Licenca: MIT
- Evidencia da licenca: https://github.com/fastapi/fastapi/blob/master/LICENSE

## Criterios verificados

A fonte foi aprovada apos confirmar:

- um diretorio nao-root dedicado a documentacao tecnica em portugues brasileiro;
- historico estavel e manutencao recente no path selecionado;
- licenca publica e clara;
- prosa tecnica coerente em tutoriais e guias de FastAPI;
- material suficiente para construir o conjunto de avaliacao planejado.

A consulta realizada em 2026-07-13 encontrou 124 arquivos Markdown/MDX em `docs/pt/docs`. A arvore consultada nao estava truncada. Essa contagem e um snapshot e deve ser reconfirmada antes da ingestao.

## Ressalvas

- Algumas paginas referenciam snippets Python em `docs_src`, fora do path selecionado. Uma ingestao restrita ao Markdown preservara a explicacao, mas nao resolvera automaticamente esses exemplos externos.
- A documentacao usa diretivas proprias do gerador, incluindo blocos como `/// tip` e marcadores de inclusao. A normalizacao deve evitar que essa sintaxe introduza ruido nos chunks.
- O diretorio usa o codigo `pt`, embora a prosa verificada seja PT-BR e o idioma aprovado para a avaliacao seja `pt-BR`.

## Dataset de avaliacao 16+4

O arquivo `questions.jsonl` contem 20 perguntas curadas a partir da fonte aprovada:

- 16 perguntas respondiveis por paths e secoes publicas em `docs/pt/docs`;
- 4 perguntas plausiveis, mas deliberadamente nao suportadas pela fonte aprovada.

Cada linha do JSONL usa o schema:

- `id`: identificador unico;
- `question`: pergunta em portugues brasileiro;
- `answerable`: `true` para casos suportados, `false` para casos nao suportados;
- `expected_state`: `answered` ou `insufficient_evidence`;
- `expected_paths`: paths esperados para casos respondiveis;
- `expected_sections`: secoes Markdown esperadas para casos respondiveis.

## Gate de release

O runner `backend/scripts/evaluate_retrieval.py` valida estritamente o dataset e executa as perguntas contra a versao ativa indexada da fonte aprovada. O processo sai com codigo `0` somente quando:

- pelo menos 14 das 16 perguntas respondiveis tem acerto Top-3 em path e secao esperados;
- todas as 4 perguntas nao suportadas retornam `insufficient_evidence`;
- todas as sentencas da resposta estao validadas contra o chunk citado.

Comando padrao:

```bash
PYENV_VERSION=3.12.13 PYTHONPATH=backend python backend/scripts/evaluate_retrieval.py \
  --dataset evaluation/pt-br/questions.jsonl \
  --top-k 3 \
  --output evaluation/pt-br/latest-report.json
```

`latest-report.json` e um artefato local gerado sob demanda e nao deve ser tratado como fonte curada.
