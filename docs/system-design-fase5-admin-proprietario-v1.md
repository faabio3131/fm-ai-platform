# Fase 5 — System Design — Administração / Proprietário V1

Status: APROVADO PARA IMPLEMENTAÇÃO na branch de trabalho da Fase 5.

## 1. Objetivo

Implementar o Painel Proprietário / Administrador como composição comercial das
autoridades já existentes do Kordena, sem criar um segundo sistema de identidade,
pagamento, estoque, integração ou auditoria.

O painel deve permitir operação normal sem editar código ou `.env` e preservar:
tenant/unidade, RBAC, PIN administrativo, auditoria, segredos protegidos,
idempotência e compatibilidade com o runtime já homologado.

## 2. Autoridades de dados

| Capacidade | Autoridade |
|---|---|
| autenticação, usuário, papéis, unidades permitidas | `fm_usuarios_v1`, `fm_usuario_papeis_v1`, `fm_usuario_unidades_v1` |
| PIN e autorização administrativa | segurança V1 existente |
| cadastro administrativo da empresa/unidades | novo cadastro aditivo `fm_empresas_admin_v1` / `fm_unidades_admin_v1` |
| parâmetros operacionais e financeiros não secretos | `fm_configuracoes_estabelecimento_v1` |
| gateways/PIX/credenciais | Control Plane de integrações + Secret Vault existentes |
| pedidos | `pedidos_v1` |
| vendas reconhecidas | `vendas_financeiras_v1` |
| pagamentos | `pagamentos_v1` |
| estoque | `estoque_saldos_v1` e catálogo/ficha autoritativos existentes |
| entrega | `entregas_v1` |
| auditoria | `fm_auditoria_v1` |
| saúde das integrações | `fm_servicos_externos_config_v1` + healthchecks existentes |

A Fase 5 não armazenará tokens, chaves PIX privadas, senhas, PINs ou credenciais
bancárias nos novos registros administrativos.

## 3. Novo schema mínimo

### fm_empresas_admin_v1
Metadados empresariais não secretos do tenant: nome empresarial/exibição, moeda,
timezone, ativo e versão.

### fm_unidades_admin_v1
Uma linha por tenant/unidade: nome, código, matriz/filial, dados cadastrais,
endereço comercial, horários, ativa, versão e timestamps.

### fm_configuracoes_estabelecimento_v1
Configuração não secreta por unidade: formas de pagamento habilitadas, taxa de
serviço, parâmetros operacionais, política financeira pública e versão.

A migration 0036 é aditiva e faz backfill determinístico a partir das identidades
e do mapping de loja legado quando disponível. Nenhuma unidade existente é
inventada fora dos escopos já observados.

## 4. Escritas administrativas

Toda escrita:
1. exige identidade autenticada;
2. exige `ADMIN_ACESSAR` e permissão específica;
3. ocorre somente no tenant da identidade;
4. restringe unidade às unidades administráveis do tenant;
5. usa versão esperada para atualização quando aplicável;
6. registra auditoria antes/depois com dados resumidos e sem segredos;
7. é confirmada em transação própria da aplicação.

Alterações sensíveis continuam exigindo o PIN administrativo já implementado na
UI. Integrações/credenciais continuam delegadas à página/control plane existente.

## 5. Usuários e permissões

Não será criado outro cadastro de usuários.

A Fase 5 amplia o repositório canônico de identidades apenas com operações
administrativas ausentes:
- listar usuários do tenant;
- definir papéis;
- definir unidades permitidas e unidade padrão;
- ativar/desativar;
- conceder/revogar acesso administrativo sensível.

Permissões continuam derivadas da matriz de papéis canônica. A UI mostra a matriz
efetiva para evitar a falsa impressão de permissões customizadas inexistentes.

## 6. Dashboard e relatórios

A aplicação de leitura administrativa consulta somente tabelas autoritativas e
pode consolidar todas as unidades do mesmo tenant.

Indicadores mínimos:
- pedidos;
- vendas financeiras reconhecidas;
- pagamentos pagos/pendentes/estornados;
- ticket médio reconhecido;
- estoque físico/reservado;
- entregas por estado;
- integrações configuradas/homologadas;
- usuários ativos;
- auditoria recente.

CMV/margem só será mostrado quando houver fonte verificável no escopo. Se a
origem atual for catálogo/ficha vigente e não custo histórico congelado, a UI
deve rotular o valor como estimativa atual, nunca como CMV contábil histórico.

## 7. Falhas e fail-closed

- tenant divergente: negar;
- unidade fora do tenant/escopo administrativo: negar;
- versão concorrente: negar e pedir recarga;
- schema ausente: gate/migration, nunca criar tabela silenciosamente na UI;
- integração não configurada: mostrar estado, nunca simular saúde;
- segredo: nunca ler/reexibir valor bruto;
- erro de relatório: isolar o bloco e não efetuar escrita.

## 8. Gate da Fase 5

Aprovação exige:
- migration 0036 em PostgreSQL;
- testes unitários/integração de CRUD, isolamento, concorrência e auditoria;
- testes de usuários/papéis/unidades;
- dashboard consolidado e unitário;
- navegador real com PIN, edição administrativa e bloqueio de perfil sem acesso;
- regressão Auth/RBAC, integrações e Fase 4;
- nenhum segredo exposto;
- administração comercial normal sem código/`.env`.

Merge/deploy continuam fora do escopo deste gate.
