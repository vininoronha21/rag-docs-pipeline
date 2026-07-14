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

## Gate futuro 16+4

Antes de iniciar a fase de avaliacao, deve ser criado e revisado um conjunto com:

- 16 perguntas respondiveis pela fonte aprovada;
- 4 perguntas deliberadamente nao suportadas pela fonte.

As perguntas definitivas nao fazem parte desta tarefa. Cada pergunta devera ser validada contra o corpus ingerido para confirmar sua classificacao e evitar ambiguidade.
