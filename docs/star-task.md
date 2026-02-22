# Star Task Assistant

The Star Task assistant is analytics-only. It never changes routing decisions or writes operational data.

## Safety model

- The LLM is used only for `intent + filter extraction`.
- Intent execution is hard-mapped to allowlisted internal analytics functions.
- No arbitrary SQL from prompts.
- UI scope is enforced as intersection:
  - `run_id` from scope cannot be overridden.
  - `office` from scope cannot be broadened.
  - `date_from/date_to` are intersected and never expanded.
- Unknown filters are ignored.

## Supported intents

- `office_distribution`
- `manager_workload`
- `avg_priority_by_office`
- `ticket_type_distribution`
- `sentiment_distribution`
- `language_distribution`
- `vip_priority_breakdown`
- `unassigned_rate_and_reasons`
- `processing_time_stats`
- `trend_over_time`
- `top_entities`
- `cross_tab_type_by_office`
- `cross_tab_sentiment_by_office`
- `ticket_count_by_city`
- `average_age_by_office`
- `custom_filtered_summary`

## Response shapes

### Result

```json
{
  "kind": "result",
  "intent": "sentiment_distribution",
  "title": "Sentiment distribution",
  "chart_type": "donut",
  "data": { "labels": ["Positive", "Neutral", "Negative"], "values": [10, 20, 5] },
  "table": [{ "tone": "Neutral", "count": 20 }],
  "explanation": "Distribution of sentiment labels in the selected scope.",
  "filters": { "office_names": [], "cities": [], "run_id": "..." },
  "computed_from": "ai_analysis join tickets join assignments join business_units",
  "scope_applied": { "run_id": "...", "office": null, "date_from": null, "date_to": null },
  "warnings": [],
  "used_fallback": false,
  "cache_hit": false
}
```

### Clarification

```json
{
  "kind": "clarification",
  "title": "Please clarify your analytics request",
  "explanation": "Choose one of these suggestions...",
  "options": [
    {
      "intent": "ticket_type_distribution",
      "label": "Ticket type distribution",
      "query_hint": "Show ticket type distribution"
    }
  ],
  "filters": { "office_names": [], "cities": [], "run_id": "..." },
  "scope_applied": { "run_id": "...", "office": null, "date_from": null, "date_to": null },
  "warnings": []
}
```

## Example queries

- `Tickets by office`
- `Sentiment distribution for Astana`
- `Average priority by office from 2026-02-01 to 2026-02-20`
- `Top managers by assigned tickets`
- `VIP vs Mass breakdown`
- `Unassigned rate and reasons`
- `Processing time p95 by office`
- `Trend by day`
