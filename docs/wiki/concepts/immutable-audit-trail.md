---
title: Immutable Audit Trail
type: concept
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - audit
  - security
project: fraud-detector
sources:
  - src/models/audit_entry.py
  - src/services/audit.py
aliases:
  - audit trail
source_repository: .
source_revision: 44829d2
source_paths:
  - src/models/audit_entry.py
  - src/services/audit.py
---

# Immutable Audit Trail

## Definition

Registro append-only de decisiones de scoring y acciones de analistas con checksum SHA-256.

## Key facts

`AuditEntry` conserva actor, transacción, acción, estados, detalles, timestamp y `sha256_checksum`. Usa `Base` directamente y no tiene `updated_at`.

## Interpretation

Permite reconstruir por qué cambió un estado y detectar alteraciones de los detalles registrados.

## Practical application

[[tools/fraud-detector-api-contract]] y [[runbooks/end-to-end-debugging]].

## Uncertainty

La inmutabilidad se aplica por diseño y flujo de servicio; cualquier mecanismo externo de modificación DB debe considerarse fuera del contrato de aplicación.

## Related

- [[entities/fraud-detector-domain-model]]
- [[decisions/fraud-detector-architecture]]

## Sources

- `src/models/audit_entry.py`
- `src/services/audit.py`
