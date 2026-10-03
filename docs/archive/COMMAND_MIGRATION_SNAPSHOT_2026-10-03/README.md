# Snapshot isolado — migração Kordena → FM Command

Data: 2026-10-03

## Objetivo

Preservar, dentro do repositório do Kordena e fora do runtime do produto, uma cópia verificável da migração dos diagnósticos técnicos de plataforma que não devem permanecer na área do cliente.

Este material é **arquivo de segurança / referência de recuperação**. Não deve ser importado, executado, publicado nem incluído no bundle do Kordena.

## Decisão arquitetural

- O Kordena cliente não deve expor detalhes técnicos de infraestrutura como FastAPI, backend, banco, endpoints de health/readiness ou fronteiras técnicas da plataforma.
- Esses diagnósticos pertencem ao **FM Command**, sob responsabilidade da FM Tecnologia.
- O cliente deve visualizar somente estados operacionais/comerciais relevantes ao próprio negócio.
- A implementação do FM Command continua bloqueada para merge enquanto outra correção maior do Command estiver em andamento.

## Artefatos preservados

1. `kordena-system-health-original.tsx`
   - cópia exata da antiga tela técnica do Kordena antes da remoção;
   - origem: `fm-ai-platform:web/src/app/admin/system-health/page.tsx`;
   - blob SHA: `c16a8804fece2222f2383a6aef29fbc5b9764cfd`.

2. `kordena-module-registry-original.ts`
   - cópia exata do registry original contendo a entrada `Saúde do sistema`;
   - origem: `fm-ai-platform:web/src/features/shell/module-registry.ts`;
   - blob SHA: `c00d5f2e71e91abbae08a9007ad5adc9a0f499c2`.

3. `command-operations-page-migrated.tsx`
   - cópia exata da tela de Operações do FM Command após receber a seção `Saúde técnica da plataforma`;
   - origem: `FM-CONTROL-CENTER:src/app/dashboard/operations/page.tsx`;
   - branch de origem: `fix/command-centralize-platform-health`;
   - blob SHA: `1fbda1b0801b3140fd8d6b1b4e8e0dd26f88b364`.

4. `command-operations-ui-test-migrated.ts`
   - cópia exata do teste de regressão correspondente no FM Command;
   - origem: `FM-CONTROL-CENTER:tests/operations-ui.unit.test.ts`;
   - branch de origem: `fix/command-centralize-platform-health`;
   - blob SHA: `111f74d862f4a436f947e7e1c3a0fc55130b13ac`.

## Referências de PR

- Kordena — remoção da saúde técnica: PR #181
- FM Command — centralização da saúde técnica: PR #41
- PR #41 está marcada como **BLOQUEADO / NÃO MERGEAR** até reconciliação com o CURRENT final do Command.

## Regra de recuperação

Se for necessário recuperar essa migração no futuro:

1. tratar estes arquivos apenas como snapshot de referência;
2. primeiro buscar o CURRENT real do FM Command;
3. comparar o CURRENT com este snapshot;
4. reaplicar somente o delta ainda necessário;
5. executar testes e gates completos;
6. nunca sobrescrever cegamente arquivos atuais do Command.

## Isolamento

Esta pasta está armazenada em uma branch de arquivo dedicada:
`archive/command-migration-snapshot-20261003`

Nenhum arquivo desta pasta participa do runtime do Kordena.
Nenhum deploy deve ser disparado a partir desta branch.
