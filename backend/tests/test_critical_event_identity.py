import unittest
from dataclasses import replace
from uuid import uuid4

from app.critical_events.identity import (
    AuthenticatedCollector,
    RegistryBinding,
    EventIdentity,
    UnauthorizedSource,
    IdentityConflict,
    authorize_source,
    same_retry,
)


class CriticalSourceAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.tenant, self.source, self.installation, self.config = (
            uuid4() for _ in range(4)
        )
        self.principal = AuthenticatedCollector(
            "registry-client", self.installation, 2, True
        )
        self.binding = RegistryBinding(
            self.tenant,
            self.source,
            self.installation,
            self.config,
            "registry-client",
            2,
            self.tenant,
            self.source,
            self.config,
            "QA",
            frozenset({"critical-event:submit"}),
        )
        self.claim = dict(
            tenant_id=self.tenant,
            source_id=self.source,
            collector_id=self.installation,
            environment="QA",
        )

    def test_current_server_binding_accepts_only_exact_registered_authority(self):
        self.assertIs(
            authorize_source(self.principal, self.binding, **self.claim), self.binding
        )
        for field in ("tenant_id", "source_id", "collector_id"):
            with self.subTest(field=field), self.assertRaises(UnauthorizedSource):
                authorize_source(
                    self.principal, self.binding, **{**self.claim, field: uuid4()}
                )

    def test_missing_disabled_deleted_or_reassigned_registry_binding_denies(self):
        for binding in [
            None,
            *[
                replace(self.binding, **{flag: False})
                for flag in (
                    "tenant_active",
                    "source_enabled",
                    "collector_enabled",
                    "installation_enabled",
                    "credential_current",
                )
            ],
            replace(self.binding, source_owner_id=uuid4()),
            replace(self.binding, collector_source_id=uuid4()),
            replace(self.binding, installation_collector_id=uuid4()),
        ]:
            with self.subTest(binding=binding), self.assertRaises(UnauthorizedSource):
                authorize_source(self.principal, binding, **self.claim)

    def test_payload_and_untrusted_transport_cannot_grant_or_recover_authority(self):
        for principal in [
            None,
            self.claim,
            replace(self.principal, mtls_verified=False),
            replace(self.principal, generation=1),
            replace(self.principal, installation_id=uuid4()),
            replace(self.principal, principal_id="forged-header"),
        ]:
            with self.subTest(principal=principal), self.assertRaises(
                UnauthorizedSource
            ):
                authorize_source(principal, self.binding, **self.claim)
        for binding in [
            replace(self.binding, capabilities=frozenset()),
            replace(self.binding, environment="PROD"),
        ]:
            with self.assertRaises(UnauthorizedSource):
                authorize_source(self.principal, binding, **self.claim)
        with self.assertRaises(UnauthorizedSource):
            authorize_source(
                self.principal,
                self.binding,
                **self.claim,
                capability="recover:source-events"
            )

    def test_retry_hash_and_version_conflicts_never_overwrite_original_identity(self):
        original = EventIdentity(
            self.tenant, self.source, "native-event", b"a" * 32, "1.0", "1.0"
        )
        self.assertTrue(same_retry(original, replace(original)))
        for changed in [
            replace(original, payload_sha256=b"b" * 32),
            replace(original, tenant_id=uuid4()),
            replace(original, source_id=uuid4()),
            replace(original, event_id="new-id"),
            replace(original, schema_version="2.0"),
            replace(original, canonicalization_version="2.0"),
        ]:
            with self.assertRaises(IdentityConflict):
                same_retry(original, changed)
        self.assertEqual(original.payload_sha256, b"a" * 32)
        with self.assertRaises(ValueError):
            replace(original, payload_sha256=b"short")
