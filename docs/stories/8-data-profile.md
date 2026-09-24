# Data profile stories

Give every source the same first look: its archives imported and verified, a `manifest.json`, and a `profile.json`.
Shared rules and the story template are in [stories.md](../stories.md).

**Glossary for this file**
- **Slice**: one release zip of a source, e.g. `hubspot_slice_0002.zip`. The release is EnterpriseRAG-Bench `v1.0.0`.
- **dsid**: the 32-hex id at the front of every file name. The benchmark scores by it.
- **`manifest.json`** (per source, `data/<source>/manifest.json`): the release's slices with url, sha256 and document count. Same shape Gmail already had.
- **`profile.json`**: counts only, no rule decided. Confluence, Gmail and Slack already have theirs and are not touched.

---

## DATA-1  Import, manifest and profile for the remaining sources  ✅

**Status:** Done

**As a** pipeline developer
**I want to** every source to have verified archives, a `manifest.json` and a `profile.json`
**So that** each source's design can quote measured numbers, and a changed corpus is caught by sha256

**Acceptance Criteria (Gherkin)**
- Given a source with no local archives, When I run `python -m tools.import_sources <source>`, Then its slices are downloaded, each equals the sha256 the release publishes, and `raw/` and `manifest.json` exist
- Given a zip already on disk with a different sha256, When I import, Then it fails and nothing is written
- Given the six sources without a profile, When I run `python -m tools.profile_all <source>...`, Then each gets `profile.json` with files, bytes, empty files, repeated dsids, JSON-escaped files, and chars/tokens/lines percentiles

**Example with real data** (measured 2026-09-23; document counts equal the source rows of the release's `documents` parquet, 511,962 rows in all)

| source | files | bytes | median tokens | max tokens | repeated dsids |
|---|---|---|---|---|---|
| fireflies | 10,173 | 117.8 MB | 2,779 | 10,334 | 0 |
| github | 8,052 | 38.2 MB | 1,158 | 3,459 | 0 |
| google_drive | 25,108 | 178.6 MB | 1,762 | 5,676 | 0 |
| hubspot | 15,017 | 46.8 MB | 748 | 2,044 | 0 |
| jira | 6,120 | 34.0 MB | 1,391 | 2,608 | 1 |
| linear | 35,308 | 182.4 MB | 1,254 | 4,345 | 0 |

Median and max are token counts (4 chars per token). No source has an empty file or a JSON-escaped file. One Jira dsid appears twice: a later story must decide what to do with it.
Manifests also written for Linear and Slack (58 slices, 285,605 files).

**Non-functional Requirements**
- Shared NFRs in [stories.md](../stories.md). The importer is the one tool that uses the network; the profiler is deterministic and offline.
- `data/` is gitignored; only the tools and tests are committed.

**Dependencies**
- Uses: none. Service Bus: N/A · Database: N/A · UI: N/A
