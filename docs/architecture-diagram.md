```mermaid
flowchart TD
    classDef process fill:#e3f2fd,stroke:#1976d2,stroke-width:2px;
    classDef external fill:#fff3e0,stroke:#f57c00,stroke-width:2px;
    classDef output fill:#e8f5e9,stroke:#388e3c,stroke-width:2px;
    classDef guardrail fill:#ffebee,stroke:#c62828,stroke-width:2px;
    classDef telemetry fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px;
    classDef future fill:#eeeeee,stroke:#9e9e9e,stroke-width:1px,stroke-dasharray: 5 5;
    classDef errorpath fill:#fff9c4,stroke:#f9a825,stroke-width:2px;

    subgraph Graph [LangGraph Orchestrator — deterministic control flow, LLM only in Node 6]
        NodeSync[Node 0: check_and_sync_data<br/>live: check freshness, download if newer<br/>pinned: use committed snapshot]:::process
        NodeSync -->|metadata check| CKAN((DATASUS / CKAN<br/>metadata API)):::external
        CKAN -.->|last_modified or error| NodeSync
        NodeSync -.->|used_cache_after_error| NodeSyncFallback[Fallback: last cached CSV]:::errorpath
        NodeSyncFallback -.-> NodeLoad
        NodeSync --> NodeLoad

        NodeLoad[Node 1: load_and_clean<br/>ETL, PII strip, exclusion log,<br/>loads DuckDB connection]:::process
        NodeLoad --> NodeMetrics

        NodeMetrics[Node 2: compute_metrics<br/>DuckDB SQL tool functions]:::process
        NodeMetrics --> NodeChart[Node 3: generate_charts<br/>matplotlib, deterministic]:::process
        NodeChart --> NodeNews[Node 4: fetch_news]:::process

        NodeNews -->|templated query,<br/>domain allowlist| Tavily((Tavily API)):::external
        Tavily -.->|articles or failure| NodeNews
        NodeNews -.->|news_source=unavailable| NodeSanitize

        NodeNews --> NodeSanitize{Node 5: sanitize_news<br/>injection scan +<br/>delimiter escaping}:::guardrail
        NodeSanitize --> NodeReport[Node 6: synthesize_narrative<br/>only LLM call]:::process

        NodeMetrics -.->|metrics + literal SQL + definitions| NodeReport
        NodeChart -.->|file paths| NodeReport

        NodeReport --> NodeValidate{Node 7: validate_narrative<br/>numeric grounding +<br/>source grounding}:::guardrail
        NodeValidate -- mismatch, retry ≤ 3 --> NodeReport
        NodeValidate -- exhausted retries --> NodeFlagged[Flagged publish path:<br/>strip unverified claims,<br/>add validation notice]:::errorpath
        NodeValidate -- passed --> NodeRender[Node 8: render_report<br/>Markdown + charts + sources]:::output
        NodeFlagged --> NodeRender

        NodeRender --> FinalReport[/Timestamped Markdown Report<br/>America/Sao_Paulo/]:::output
    end

    subgraph Observability [Observability & Audit]
        NodeSync -.->|trace: data_check_result| Langfuse[(Langfuse Server)]:::telemetry
        NodeLoad -.->|trace: exclusion_log, source hash| Langfuse
        NodeMetrics -.->|trace: SQL + result| Langfuse
        NodeNews -.->|trace: query + result| Langfuse
        NodeReport -.->|trace: prompt+completion+tokens| Langfuse
        NodeValidate -.->|trace: diff result| Langfuse
        NodeRender -.->|self-contained structured JSON| AuditLog[/audit_log.json/]:::output
    end

    subgraph FutureWork [Documented future evolution — not built in v1]
        Checkpointer[LangGraph Checkpointer<br/>if human-approval gate added]:::future
        NeMo[NeMo Guardrails<br/>if chat interface added]:::future
        VectorDB[pgvector RAG<br/>if data-dictionary grounding scaled]:::future
        RealDB[Postgres<br/>if concurrency/scale grows —<br/>trivial swap from DuckDB]:::future
    end
```
