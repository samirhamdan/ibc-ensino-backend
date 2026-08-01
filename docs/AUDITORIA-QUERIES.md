# AUDITORIA-QUERIES — Etapa 3.4 (queries órfãs de filtro de tenant)

Gerado por `python scripts/audit_queries.py`. Toda query em tabela
com `tenant_id` deve filtrar por tenant (ou usar `get_scoped*`).

**Nenhuma query órfã encontrada.** Todas as consultas a tabelas
tenant-scoped passam por filtro de tenant ou helpers escopados.
