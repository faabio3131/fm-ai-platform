# fm-ai-platform

## Configuração do Gemini

A integração usa exclusivamente variáveis de ambiente; nenhuma credencial deve
ser adicionada ao repositório.

- `GEMINI_API_KEY` (**obrigatória**): chave da API Google Gemini. Na ausência da
  chave, os recursos de IA permanecem desativados e o gateway retorna uma mensagem
  segura de configuração.
- `GEMINI_MODEL` (opcional): nome de um modelo retornado para a chave atual com
  suporte a `generateContent`. Tanto `gemini-...` quanto `models/gemini-...` são
  aceitos. O gateway normaliza e valida o valor antes de gerar conteúdo.

Sem `GEMINI_MODEL`, o gateway consulta a lista uma única vez e escolhe o primeiro
modelo estável disponível nesta ordem: `gemini-3.6-flash` e, caso ele não esteja
disponível para a conta, outro modelo Flash estável retornado pela API.
Identificadores `preview`, `experimental`, `exp` e `latest` nunca são escolhidos
automaticamente. Os modelos desativados `gemini-2.0-flash` e
`gemini-2.0-flash-001` são sempre rejeitados, inclusive quando definidos em
`GEMINI_MODEL`.

### Diagnóstico de disponibilidade

Execute localmente, com `GEMINI_API_KEY` já definida no ambiente (a chave não é
impressa nem gravada):

```bash
python -c "from gemini_config import list_generate_content_models; print(*list_generate_content_models(), sep='\n')"
```

O ambiente de desenvolvimento desta alteração não possuía a chave. Por isso, a
descoberta e a seleção foram cobertas com mocks, mas o modelo final da conta deve
ser confirmado executando o diagnóstico acima no ambiente de implantação.
