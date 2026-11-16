"""S02-ID-01 admission policy over a freshly server-resolved registry snapshot.

These values must come from the authenticated transport and locked registry,
never from a request-body binding or forwarded client identity header. This
module exposes no HTTP authentication, enrollment or durability receipt.
"""

from dataclasses import dataclass
from uuid import UUID


class UnauthorizedSource(ValueError):
    pass


class IdentityConflict(ValueError):
    pass


@dataclass(frozen=True)
class AuthenticatedCollector:
    principal_id: str
    installation_id: UUID
    generation: int
    mtls_verified: bool


@dataclass(frozen=True)
class RegistryBinding:
    tenant_id: UUID
    source_id: UUID
    installation_id: UUID
    configuration_collector_id: UUID
    principal_id: str
    generation: int
    source_owner_id: UUID
    collector_source_id: UUID
    installation_collector_id: UUID
    environment: str
    capabilities: frozenset[str]
    tenant_active: bool = True
    source_enabled: bool = True
    collector_enabled: bool = True
    installation_enabled: bool = True
    credential_current: bool = True


def authorize_source(
    principal,
    binding,
    *,
    tenant_id,
    source_id,
    collector_id,
    environment,
    capability="critical-event:submit"
):
    """Deny missing, stale, disabled, reassigned and cross-customer authorities."""
    if not isinstance(principal, AuthenticatedCollector) or not isinstance(
        binding, RegistryBinding
    ):
        raise UnauthorizedSource("Authenticated registered source required")
    allowed = (
        principal.mtls_verified is True
        and bool(principal.principal_id)
        and principal.principal_id == binding.principal_id
        and principal.installation_id == binding.installation_id == collector_id
        and principal.generation == binding.generation
        and binding.generation > 0
        and binding.tenant_id == binding.source_owner_id == tenant_id
        and binding.source_id == binding.collector_source_id == source_id
        and binding.configuration_collector_id == binding.installation_collector_id
        and bool(environment)
        and binding.environment == environment
        and capability in binding.capabilities
        and all(
            flag is True
            for flag in (
                binding.tenant_active,
                binding.source_enabled,
                binding.collector_enabled,
                binding.installation_enabled,
                binding.credential_current,
            )
        )
    )
    if not allowed:
        raise UnauthorizedSource("Source authority unavailable")
    return binding


@dataclass(frozen=True)
class EventIdentity:
    tenant_id: UUID
    source_id: UUID
    event_id: str
    payload_sha256: bytes
    schema_version: str
    canonicalization_version: str

    def __post_init__(self):
        if (
            not isinstance(self.tenant_id, UUID)
            or not isinstance(self.source_id, UUID)
            or not isinstance(self.event_id, str)
            or not self.event_id.strip()
            or len(self.event_id) > 512
            or not isinstance(self.payload_sha256, bytes)
            or len(self.payload_sha256) != 32
            or not self.schema_version
            or not self.canonicalization_version
        ):
            raise ValueError("Invalid critical event identity")


def same_retry(existing, incoming):
    """A replay must preserve identity, exact content digest and both versions."""
    if (
        not isinstance(existing, EventIdentity)
        or not isinstance(incoming, EventIdentity)
        or existing != incoming
    ):
        raise IdentityConflict("Event identity, digest or version differs")
    return True
