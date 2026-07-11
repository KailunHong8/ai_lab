# Change Spec - Multi-Source Research Workflow (Hybrid Manual + Perplexity)

Date: 2026-06-19
Status: Proposed (design context for implementation)
Owner: Quant app

---

## 1) Problem Statement

The current research workflow works well for manual ARK-centric ingestion, but it does not scale cleanly to multiple fund sources (ARK, GMO, Sequoia, Bridgewater) plus Perplexity-generated market context.

Today, the system has two friction points:

1. Ingestion and indexing logic still contains ARK-specific routing in multiple places.
2. Perplexity is used for chat-time research, but its findings are not persisted as structured knowledge.

The result is a split mental model and inconsistent provenance.

---

## 2) Goals

1. Keep long-term investing principles curated and manual-only.
2. Generalize fund-opinion ingestion from ARK-only to multi-source.
3. Add optional Perplexity persistence for timely market context.
4. Preserve provenance, recency, and reliability metadata so the agent can reason transparently.
5. Keep UX simple for a single-user investor workflow.

---

## 3) Non-Goals

1. Full enterprise compliance and approval workflows.
2. Multi-user permissions and role-based governance.
3. Fully autonomous internet ingestion from arbitrary sources.
4. Replacing the current thesis extraction model/provider stack.

---

## 4) Current State (Codebase Snapshot)

### Implemented behavior

1. Manual upload/paste and mbox import via Research tab and knowledge upload endpoint.
2. Thesis extraction and entity relationship extraction run after ingest.
3. Principles corpus exists and is semantically searchable.
4. ARK-specific semantic corpus exists and is separately searchable.
5. Perplexity is available for chat research responses but not persisted to knowledge base.

### Current structural limits

1. Source classification currently drives ARK-vs-non-ARK branching.
2. ARK naming appears in router/service/tool contracts, making future fund expansion harder.
3. Market-opinion data and long-term principles are not yet explicitly modeled as separate corpora in DB metadata.

---

## 5) Architecture Decision

Adopt a two-lane knowledge architecture:

1. Principles lane (manual only, evergreen)
2. Market-opinion lane (fund letters + Perplexity/web context, time-sensitive)

Decision on manual vs automated ingestion:

1. Keep fund letters and principles manual as canonical inputs.
2. Add Perplexity automation as optional market-context ingestion with TTL.
3. Do not merge Perplexity context into principles lane.

Rationale:

1. Manual curation protects signal quality and conviction building.
2. Automated Perplexity provides speed and breadth for current sentiment.
3. TTL prevents stale market opinions from polluting long-term reasoning.

---

## 6) Canonical Source Taxonomy

### Corpus

1. `principles` - timeless frameworks and investing philosophy.
2. `market_opinion` - fund letters, newsletter opinions, analyst/web sentiment.

### Source Type

1. `principle_text`
2. `fund_letter`
3. `web_research`
4. `user_synthesis`

### Optional channel

1. `manual_paste`
2. `file_upload`
3. `mbox`
4. `perplexity`

### Reliability tier (for ranking/display)

1. Tier 1: principles
2. Tier 2: fund letters
3. Tier 3: user synthesis
4. Tier 4: web research / market sentiment

---

## 7) Data Model Changes (Proposed)

### Document additions

1. `corpus` (principles | market_opinion)
2. `source_type` (principle_text | fund_letter | web_research | user_synthesis)
3. `fund` (optional string, e.g. ARK, GMO, Sequoia, Bridgewater)
4. `channel` (manual_paste | file_upload | mbox | perplexity)
5. `reliability_tier` (int)
6. `published_at` (optional)
7. `ingested_at` (datetime)
8. `recency_flag` (evergreen | timely | stale)
9. `expiration_at` (optional for TTL)
10. `citations_json` (optional JSON list for web research references)
11. `ingestion_job_id` (optional)

### Thesis additions

1. `source_type`
2. `fund`
3. `reliability_tier`
4. `recency_flag`
5. `expiration_at`

### Migration note

Because DB setup currently relies on `create_all`, schema evolution will require explicit migration scripts for existing databases.

---

## 8) Service/API Changes (Proposed)

### Knowledge ingestion

1. Keep existing manual upload endpoint.
2. Add a user-facing endpoint to run and persist Perplexity research in one action:
   - Input (from user/UI): query, topic.
   - Backend action: call Perplexity, receive response content + citations, generate tags via LLM metadata enrichment, persist document, run extraction/indexing.
   - Output: created document id + extraction/indexing status + stored citation count.
3. Optional internal endpoint (service-to-service) can accept raw Perplexity payload when needed:
   - Input: response content + citations + metadata.
   - Output: created document id + extraction/indexing status.

### Perplexity input contract (user-facing)

Use a compact payload from UI:

1. `query` (string): the actual research request sent to Perplexity.
2. `topic` (string): high-level bucket for organization and filtering.
3. `tags` (string array): generated by backend LLM from query + response content + citations.

Example payload:

```json
{
   "query": "What are the latest institutional concerns about AI capex saturation in semiconductors?",
   "topic": "AI Infrastructure"
}
```

Generated metadata example (internal result):

```json
{
  "tags": ["semiconductors", "market-sentiment", "capex", "NVDA", "TSM"]
}
```

### Trigger model for Perplexity ingestion

1. Default trigger: manual user action (button/action in UI or explicit API call).
2. Optional future trigger: scheduled runs (disabled by default).
3. First implementation scope: manual trigger only.

### Retrieval

1. Keep principles search endpoint/tool for evergreen references.
2. Introduce generic market-opinion search endpoint/tool.
3. Extend thesis search filters with `corpus`, `source_type`, `fund`, and recency controls.

### Vector collection decision

1. Use one market-opinion vector collection.
2. Differentiate sources (ARK/GMO/Sequoia/Bridgewater/Perplexity) via metadata filters, not per-source collections.

---

## 9) Agent Reasoning Policy (Target)

When answering investment questions:

1. Ground with principles first (framework and risk logic).
2. Layer fund opinions second (manager theses and positioning views).
3. Layer Perplexity/web context last as time-sensitive context.
4. Always label source and date.
5. Distinguish facts vs forecasts/opinions explicitly.

Never use market sentiment alone as the core recommendation basis.

---

## 10) UX/Product Workflow (Target)

Research area should be split conceptually into two flows:

1. Principles Library (manual only)
   - Upload curated books/philosophy docs.
   - No auto web ingestion.

2. Market Research Library (manual + optional auto)
   - Manual paste/upload for fund letters.
   - Optional Perplexity import for current market sentiment.
   - Recency and source labels visible in UI.

Default operating mode:

1. Keep fund letters manual (ARK, GMO, Sequoia, Bridgewater).
2. Enable Perplexity persistence with strict TTL for web sentiment.
3. Review generated theses weekly and prune low-quality/stale entries.

---

## 11) Implementation Plan (One Shot)

Implement in one integrated change set:

1. Add taxonomy fields to DB models and wire them into existing manual ingestion.
2. Remove ARK-only assumptions in branching logic (replace with corpus/source_type rules).
3. Add Perplexity ingest endpoint (manual trigger) with citations + topic metadata.
4. Persist citations and set TTL metadata for web research entries.
5. Run thesis extraction and market-opinion indexing for persisted Perplexity outputs.
6. Add generic market-opinion search tool and prompt updates for tiered reasoning.
7. Rename/generalize ARK-specific paths directly in this change set.
8. Add stale-data cleanup behavior using `expiration_at`.

---

## 12) Acceptance Criteria

1. A document from ARK, GMO, Sequoia, and Bridgewater can all be ingested without ARK-specific branching.
2. Perplexity research can be persisted and appears in market-opinion retrieval with citations.
3. Principles retrieval never returns market-opinion items.
4. Agent responses label source/date and distinguish fact vs forecast.
5. Stale Perplexity entries can be filtered out and/or cleaned up by TTL.
6. Market-opinion retrieval is implemented using one shared vector collection with metadata filters.

---

## 13) Finalized Decisions

1. TTL default window for Perplexity/web research entries: 30 days.
2. Confidence-threshold workflow is removed for now.
3. Perplexity ingestion trigger is manual-only for now (no scheduler).

---

## 14) Final Recommendation

Use a hybrid workflow.

1. Keep fund letters and principles manual as canonical knowledge.
2. Add Perplexity as a controlled, expiring context layer.
3. Generalize ARK-specific code paths into source-agnostic market-opinion architecture.

This gives high signal quality, better scalability to new funds, and faster market awareness without polluting long-term investment principles.
