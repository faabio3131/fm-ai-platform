# FM Cognitive Core — Shared Service API for FM Control Center

**Status:** implementação candidata em certificação

**Branch:** `feat/shared-core-fmcc-service`

**PR:** #121
**Base:** `feat/web-parity-v1-total-original-migration`

## Objetivo

Expor o Cognitive Core existente por uma API interna versionada para consumidores como o FM Control Center, sem copiar o Core para outro repositório e sem criar um segundo runtime cognitivo.

## Arquitetura

```text
FM Control Center
  -> Core Gateway
  -> HTTPS /v1/fmcc/*
  -> Service-token auth
  -> Shared Core boundary
  -> AI Model Router canônico
  -> provider adapter governado
```

O FMCC continua responsável por:
- autenticação do usuário final;
- tenant authority;
- RBAC;
- Metric Engine;
- provenance;
- autorização determinística;
- actions.

O serviço compartilhado recebe contexto já autenticado pelo backend FMCC e possui somente duas responsabilidades cognitivas:
- planejamento sobre uma allowlist fornecida pelo consumidor;
- síntese textual sobre facts/evidence já governados.

## Endpoints

### POST /v1/fmcc/plan

Entrada:
- `question`;
- `tenantId`;
- `userId`;
- `correlationId`;
- `allowedCapabilities`.

Saída:
- `capability`;
- `arguments`.

O serviço recusa capability fora da allowlist e argumentos que tentem definir tenant, usuário, papel, permissão, token ou segredo.

### POST /v1/fmcc/synthesize

Entrada:
- `question`;
- `tenantId`;
- `userId`;
- `correlationId`;
- `facts`;
- `evidence`.

Saída:
- `answer`;
- `evidence`;
- `factualStatus`.

O modelo não pode substituir evidence nem factualStatus. Esses campos são emitidos pelo boundary governado.

## Autenticação service-to-service

O serviço exige Bearer token.

A referência é lida de:
- `FM_CORE_SERVICE_TOKEN_REF`;
- fallback controlado: `env:FM_CORE_SERVICE_TOKEN`.

O valor é resolvido via `SecretStore` e nunca deve ser persistido no repositório, documentação, payload ou log.

## Routing scope

O provider/modelo continua sendo selecionado pelo AI Model Router canônico e pelo Control Plane existente.

O serviço exige em runtime:
- `FM_CORE_ROUTING_TENANT_ID`;
- `FM_CORE_ROUTING_UNIT_ID`.

Essas variáveis identificam o escopo de configuração do modelo no Control Plane. Elas não alteram o tenant do consumidor FMCC enviado na `SolicitacaoIA`, que permanece registrado no metering.

## Capabilities do AI Router

Adicionadas:
- `fmcc_planning`;
- `fmcc_synthesis`.

Configurações Gemini homologadas sem capability explícita continuam reutilizando o mesmo control plane para as capabilities internas aprovadas, evitando duplicação de credencial/configuração.

## Fail-closed

O endpoint retorna indisponibilidade quando:
- service token não está configurado;
- service token é inválido;
- routing scope não está configurado;
- não existe rota compatível no AI Router;
- provider/control plane falha;
- saída do modelo viola contrato.

## Limites

Esta implementação não declara:
- deploy Live;
- credencial real;
- homologação externa;
- integração Preview do FMCC.

Esses estados exigem deployment, configuração segura de runtime e smoke real.
