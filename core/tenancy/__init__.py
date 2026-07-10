from core.tenancy.models import Tenant, TenantUser, TenantScopedModel, uuid7
from core.tenancy.context import (set_current_tenant, current_tenant, require_tenant,
                                  current_tenant_id, default_tenant_id, clear_default_tenant_cache,
                                  get_scoped, get_scoped_or_404)
from core.tenancy.middleware import init_tenant_middleware, clear_tenant_cache, TenantContext
from core.tenancy.auth import (role_no_tenant, vincular_usuario_ao_tenant,
                               definir_papel_no_tenant, usuarios_do_tenant_query,
                               get_user_scoped_or_404, invalidar_cache_papel,
                               tenant_user_ou_none)

__all__ = ['Tenant', 'TenantUser', 'TenantScopedModel', 'uuid7',
           'set_current_tenant', 'current_tenant', 'require_tenant',
           'current_tenant_id', 'default_tenant_id', 'clear_default_tenant_cache',
           'get_scoped', 'get_scoped_or_404',
           'init_tenant_middleware', 'clear_tenant_cache', 'TenantContext',
           'role_no_tenant', 'vincular_usuario_ao_tenant',
           'definir_papel_no_tenant', 'usuarios_do_tenant_query',
           'get_user_scoped_or_404', 'invalidar_cache_papel',
           'tenant_user_ou_none']
