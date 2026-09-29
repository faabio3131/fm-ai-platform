# ADR-KCA-006 — Command como autoridade de integrações de plataforma

Status: ADOTADO

## Contexto

Kordena possui dois grupos de integrações com autoridades diferentes:

1. serviços que fazem parte da própria infraestrutura comercial do SaaS e são
   pagos/operados pela FM Tecnologia;
2. integrações que representam contas, credenciais e contratos do estabelecimento.

Misturar esses grupos no mesmo painel do tenant fazia o cliente enxergar e poder
tentar administrar credenciais que pertencem à plataforma.

## Decisão

O painel central oficial da FM Tecnologia chama-se **Command**.

O namespace técnico histórico `FMCC` permanece temporariamente em rotas e nomes
internos para compatibilidade, mas a autoridade de negócio é o Command.

O catálogo de integrações passa a declarar explicitamente:

- `platform_managed`: autoridade FM/Command;
- `tenant_managed`: autoridade do estabelecimento.

Na V1, são `platform_managed`:

- Google Gemini / IA principal;
- Google Maps / Geocoding / Routes / browser map key.

As demais integrações do catálogo permanecem `tenant_managed`, incluindo Meta,
WhatsApp, marketplaces, pagamentos e fiscal, salvo decisão arquitetural futura.

## Superfície do tenant

A API e a UI de `/v1/admin/integracoes` não listam integrações
`platform_managed`.

Chamadas diretas de escrita, healthcheck ou homologação do tenant contra uma
integração `platform_managed` devem falhar fechado.

## Superfície do Command

O Kordena expõe uma fronteira server-to-server autenticada em:

`/v1/control-plane/fmcc/integrations`

A fronteira usa o mesmo token de control plane já governado pelo FMCC/Command,
exige step-up fresco para mutações e grava as configurações canônicas em:

- tenant técnico: `nova-fm-control-plane`;
- unidade técnica: `fm-control-center`.

O Command não cria uma segunda fonte de verdade: ele delega writes para
`AplicacaoIntegracoesAdminV1`, o mesmo serviço transacional usado pela autoridade
canônica de integrações.

## Runtime

Gemini e Maps resolvem primeiro a configuração canônica do Command.

Durante a migração existe uma ponte de compatibilidade:

- se o Command ainda não tiver configuração, o runtime pode usar a configuração
  homologada do tenant solicitante;
- se o tenant solicitante não tiver configuração, o runtime pode usar uma única
  configuração legada homologada encontrada no banco;
- se houver mais de uma candidata legada homologada, o runtime falha fechado com
  `configuracao_plataforma_legada_ambigua`.

Assim que uma configuração canônica existir no Command, o fallback legado deixa
de participar da decisão.

## Segurança

- segredos continuam cifrados no vault;
- nenhuma credencial é retornada pela API;
- o runtime resolve o segredo no escopo da configuração que foi selecionada;
- tenant comum não pode editar integrações de plataforma;
- mutações do Command exigem token server-to-server e step-up recente;
- a ponte legada nunca escolhe arbitrariamente entre múltiplas candidatas.

## Evolução

O próximo passo é o frontend privado do Command consumir esta fronteira e
centralizar healthcheck, homologação, rotação, uso, FinOps, alertas e auditoria
das APIs compartilhadas entre Kordena e os demais SaaS da FM Tecnologia.
