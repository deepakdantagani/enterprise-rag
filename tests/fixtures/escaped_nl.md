Service Catalog Contract and Integration Playbook

Summary:

This playbook defines the canonical service catalog contract for model and variant metadata and documents recommended integration patterns for runtime, Dedicated, Private deployments, and Console authoring. The catalog centralizes: model variant mappings, compatibility profiles, region/availability constraints, SLO class assignments, and operational metadata used by routing and cost-aware features.

Purpose and scope:

- Establish a single, versioned API surface for catalog CRUD operations.
- Provide concrete integration recipes for each consumer type (runtime, console, dedicated, on-prem).
- Describe rollout, monitoring, and security requirements to avoid inconsistent behavior across services.
- Scope excludes billing pipeline implementation and model training lineage.

Key principles:

1) Single source of truth: catalog entries are authoritative for routing, routing fallbacks, and console metadata.
2) Backwards-compatible evolution: additive fields only; breaking changes require major versioning.
3) Fast propagation: normal writes should be visible to runtime consumers within the defined change propagation SLO.

High-level API contract (summary):

- Base path: /api/catalog/v1/entries
- Operations: list, retrieve by id, create, update (patch), soft-delete
- Modes: read-only (runtime), read-write (authoring), bulk import (onboarding)
- Auth: bearer tokens with role claims controlling write vs read access
- Versioning: Accept-Version header; default v1; support feature-flagged v1.1 for opt-in fields

Canonical entry fields (human-readable form):

- id: stable string identifier (e.g., gv-2026-0001)
- name: human-friendly model name (namespace/name)
- variants: list of variant identifiers mapped to binary artifacts (variant IDs only)
- compatibility_profile: tag describing latency/cost compatibility (e.g., low-latency/high-cost)
- regions_allowed: list of region identifiers where routing is permitted
- cost_multiplier: decimal multiplier applied by routing/cost algorithms (optional)
- deprecation_date: ISO date when the model is scheduled for retire (optional)
- bindings: pointers to external integrations (encrypted references only)

API semantics and examples (pseudo-examples):

- List call with filters: GET /api/catalog/v1/entries?compatibility_profile=low-latency&region=us-west1 returns a paged list of matching entries. Use page_token and page_size for pagination.

- Create flow (authoring): POST /api/catalog/v1/entries with canonical entry payload. On success return 201 and Location header.

- cURL example (authoring):
  curl -H "Authorization: Bearer $SVC_TOKEN" -H "Accept-Version: v1" -X POST https://catalog.internal.redwood/api/catalog/v1/entries -d 'id: gv-2026-0001, name: redwood/gpt-3.8-f, variants: [f32, f16-q4], compatibility_profile: low-latency, regions_allowed: [us-west1]'

Integration patterns (detailed):

1) Runtime (eng-serving-runtime) - read-only cache

- Behavior: runtime processes consume a read-only snapshot. Snapshots are refreshed on a schedule (default 30s) and via a change-stream subscription (Kafka).
- Cache invalidation: entries with a higher semantic version trigger immediate refresh. Runtime must support last-known-good fallback to a pinned catalog file for >5m outages.
- Observability: runtime traces must include catalog_snapshot_version and entry_ids used for routing decisions.

2) Console and authoring services - managed write path

- Writes are mediated by an authoring service that enforces schema validation and a soft-approval workflow: draft -> approved -> published.
- Approval requirements: at least one applied-ml reviewer for compatibility changes and one eng-infra reviewer for region/binding changes.

3) Dedicated customer pools and Private (VPC/on-prem) - sync model

- Dedicated: a periodic export job writes approved entries for the customer to an encrypted customer-specific location. A tenant-local registry in the Dedicated control plane consumes the export and exposes a local read-only API.
- On-prem: installers accept a signed catalog manifest pointer argument (installer flag: --catalog-import). The import validates signatures and applies entries into the local registry.

Versioning, compatibility and rollout:

- Additive-first policy: new fields are added as optional. Renames or semantic changes require a major version (v2).
- Soft-deprecation: set deprecation_date. Consumers should stop routing to entries older than deprecation_date + 30 days.
- Canary rollout process for schema changes: enable Accept-Version opt-in for small percentage traffic (2% -> 10% -> 50% -> 100%). Wait 24 hours between steps and validate metrics and contract tests.

SLOs and Monitoring:

- Catalog API availability SLO: 99.95% monthly.
- Latency SLO: p95 GET /entries/{id} < 50ms in-region.
- Change propagation SLO: 120 seconds (time from publish to runtime visibility).

Key alerts:

- P1: API error rate > 1% sustained for 5 minutes or availability drops below 99.9%.
- P2: Change propagation lag > 10 minutes for > 5% of updates.

Instrumentation requirements:

- All writes must emit events to the catalog-change topic with schema version and correlation id.
- Runtimes must log catalog_snapshot_version in request traces and measurement tooling must correlate generation metrics with catalog versions.

Security and RBAC:

- Roles: catalog-reader, catalog-writer, catalog-admin.
- Writer endpoints require catalog-writer role; approval flows require catalog-admin for publish actions.
- Sensitive bindings MUST be stored encrypted in KMS and not returned in GET response bodies. GET responses may include a sentinel flag like "has_sensitive_bindings=true".

Testing and validation:

- Schema unit tests and contract tests must be added to the authoring CI pipeline.
- Integration test harness: staging runtime runs against a synthetic catalog with varied compatibility profiles and region constraints.
- Load testing: verify list/pagination performance with up to 100k entries at 200 RPS target.

Migration and deprecation plan (recommended timeline):

- Phase 0 (planning): publish schema docs and runbook.
- Phase 1 (30 days): run catalog service in read-only mode for runtime; no authoring writes except imports. Collect compatibility gaps.
- Phase 2 (30-60 days): enable feature-flagged authoring for internal teams (v1.1). Run canaries and expand test coverage.
- Phase 3 (60-120 days): open write access to broader teams with approval gating for region/binding changes; begin tenant sync for Dedicated.

Deprecation notice policy:

- Minimum notice: 90 days for model deprecation windows.
- Automation: the authoring service should trigger console notifications and email to owning teams and affected tenants when deprecation_date is set.

Pre-deploy checklist:

- Schema published and contract tests added to CI.
- Authoring UI wired to validator and approval service.
- RBAC policies created in IAM and tested.
- Runtime caching library implemented with last-known-good fallback.
- Dashboards: Catalog API availability, change lag, cache hit ratio.
- Security review signed off by security-and-compliance.

Owners and contacts:

- Product owner: Asha Patel (product).
- Technical owner: Daniel Kim (eng-platform).
- Applied ML contact: Marta Gonzalez (applied-ml).

Appendix: canonical schema (human-readable summary)

- required fields: id, name, variants, compatibility_profile
- optional fields: regions_allowed, cost_multiplier, deprecation_date, bindings

Example operational commands (migration):

- Export approved entries for tenant mycorp to encrypted storage:
  tools/catalog_export.py --tenant mycorp --approved --out gs://redwood-tenant-manifests/mycorp/catalog-YYYY-MM-DD.gpg

- Import a signed manifest to an onprem installer:
  ./installer --catalog-import gs://redwood-tenant-manifests/mycorp/catalog-YYYY-MM-DD.gpg --verify-signature

References and related pages:

- eng-serving-runtime/runtime-architecture (runtime cache and fallback details).
- product-docs/requirements/multimodel-pipeline-orchestration-prd-2026-01-12.json (multi-model orchestration constraints).

Revision history:

- 2026-10-15: initial draft by Asha Patel.
- 2026-11-10: added SLOs and canary rollout process after eng-platform review.
- 2026-12-01: clarified migration checklist and approval gating (current status: in_review).
