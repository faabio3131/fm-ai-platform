# Fundação de segurança e contexto V1

## Modelo de confiança

A identidade autenticada é a raiz de confiança. `tenant_id` e `unidade_id` recebidos da
interface são apenas solicitações e precisam coincidir com vínculos ativos resolvidos no
servidor. Um ID válido não concede acesso. A autorização é **deny-by-default**, é aplicada
também a administradores e identidades técnicas e produz a mesma resposta segura para
recurso inexistente ou fora do escopo.

## Contexto, tenant e unidade

`ContextoExecucao` é imutável, independente de UI/banco, exige tenant, unidade, usuário,
correlation ID, origem e instante timezone-aware. Papéis e permissões são conjuntos
distintos; unidades permitidas delimitam o escopo. Metadata é uma tupla imutável, pequena
e serializável. `ContextoExecucao.sistema` exige identidade técnica explícita e motivo
auditável. `ResolvedorTenant` e `ResolvedorUnidade` são portas; os vínculos e o adapter
in-memory demonstram resolução, unidade padrão e troca validada sem abrir banco.

Sessão ausente/expirada deve ser rejeitada pelo futuro adapter de autenticação antes da
construção do contexto. Não existe fallback para primeiro tenant ou unidade.

## RBAC, matriz e concessões

`Permissao` possui identificadores persistíveis estáveis, independentes de rótulos. A
matriz dos papéis Administrador, Gerente, Caixa, Garçom, Cozinha, Expedição, Entregador,
Atendimento, Financeiro e Gerente IA é somente baseline inicial. `Concessao` permite
adicionais, negativas (que têm precedência na futura composição), escopo por unidade,
validade, limites monetários e bloqueios críticos. Persistência e editor administrativo
não fazem parte desta entrega.

## Alçadas e ações críticas

`ResultadoAlcada` registra decisão, confirmação, aprovador, motivo, limite e valor em
`Dinheiro`, política, versão e metadata. A porta cobre por identificador de permissão os
casos de desconto, estorno, cancelamento após produção, ajuste de estoque, compra,
campanha, priorização, liberação de cozinha e ação da IA. Nesta fundação, limites
configurados são avaliados; ausência de permissão continua negando antes da alçada.
Ações críticas devem futuramente gerar `EventoAuditoria`, e confirmação/aprovação deve
ser uma credencial separada, nunca um booleano vindo do cliente.

## Autorização e IDOR

`AutorizarAcao` verifica primeiro tenant e unidade, depois permissão explícita e alçada.
Não consulta banco e retorna decisão versionável com correlation ID. `recurso_no_escopo`
serve de guarda para repositories futuros; filtros por tenant/unidade ainda deverão ser
obrigatórios na própria consulta, evitando buscar e filtrar depois. Divergências retornam
`recurso_indisponivel`, sem confirmar existência, dono ou tenant do objeto.

## Auditoria, correlação e sanitização

`EventoAuditoria` é imutável, UTC e contém ator/papel, ação, recurso com ID seguro,
resultado, motivo, origem, política/versão e correlation/causation. A porta
`RepositorioAuditoria` não define tecnologia; o adapter em memória é apenas para testes.
Helpers iniciam, validam e propagam correlation ID e geram causation ID para comandos e
eventos, preservando a origem da cadeia.

São removidas chaves relacionadas a senha, token, API key, cartão, Pix, telefone e
segredos. Valores complexos são descartados. Resumos `antes/depois` devem conter apenas
campos necessários e já sanitizados; payload integral, credencial, conteúdo privado e
identificadores pessoais completos são proibidos. Deploy real deve aplicar retenção,
controle de acesso, integridade append-only e proteção do armazenamento.

## Gerente IA

O papel começa somente com consulta operacional limitada e preparação em preview. Não
recebe caixa nem alteração financeira por padrão. Mesmo uma permissão mutável adicionada
não contorna o RBAC: a política exige confirmação humana. Não há ação automática por voz
no PDV ou caixa.

## Integração futura, não escopo e limitações

Adapters futuros deverão obter vínculos da identidade autenticada, compor matriz,
concessões/negações e validade, construir o contexto e passar a decisão aos services e à
auditoria. O rollback é remover este pacote, testes e documento.

Não há integração com `app.py`, PDV ou Mica; tela, endpoint, ORM, tabela, schema,
migration, banco e Pedido funcional permanecem inalterados. Não há persistência,
autenticação, MFA, motor configurável de políticas ou armazenamento WORM. A matriz e os
limites são defaults em código e precisam de revisão de negócio e persistência em PR
explicitamente autorizada.
