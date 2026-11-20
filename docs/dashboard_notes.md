# Dashboard Notes (Draft)

## 1. Audience and Decision

- **User:** The CEO of a Montana destination organization.
- **Decision:** Whether to increase, maintain or reduce destination marketing aimed at Canadian travelers for an upcoming month, using predicted inbound passenger crossings as an indicator of travel demand.
- **Important:** Border crossings count inbound personal-vehicle passengers at Montana's Canadian ports. They are an indicator of demand, not a confirmed count of Canadian tourists.

## 2. Questions Answered

| Page | Question | Status |
|---|---|---|
| 1 | How have inbound passenger crossings at Montana's Canadian border changed over time and by season? | Built |
| 2 | How accurately does the model predict monthly crossings, and when are its predictions least reliable? | Built |
| 3 | Based on predicted border traffic, should the organization adjust marketing aimed at Canadian travelers? | Built |
| 4 | How do border-crossing patterns differ among Montana's ports of entry? | Built |

## 3. AI Feature

`ai/generate_summaries.py` uses `claude-haiku-5-5` to write a two-sentence summary of each test prediction. The summaries are saved in PostgreSQL (`ai_summaries`), and Page 3 of the dashboard displays the saved text without making new API calls. Each reply is checked before saving: two sentences, under 55 words, and every number taken from the supplied facts.

Reusable prompt (condensed; full text in the script):

```text
You are writing for the CEO of a Montana destination organization. Write exactly
2 plain-language sentences, under 55 words in total, as one paragraph.
Sentence 1: State the predicted crossings, the actual crossings, and whether the
model predicted too high or too low.
Sentence 2: Give only the single most useful explanation for the miss that the
supplied patterns support.
Rules: Pick one explanation. Say "historical training data"; do not name years.
Use only the facts below; no weather, politics, events, marketing, border policies
or other outside information. Use cautious language ("may have", "suggests");
never say a feature caused travel to change. Do not describe passengers as
confirmed tourists or Canadian residents. Copy numbers exactly. Plain text only.

Facts for {month}: predicted {predicted}; actual {actual}; too {direction} by
{miss_size}; error {error}; previous month {crossings_lag1}; three-month average
{crossings_rolling_3}; season {season}; training average for {month_name}
{month_average} and for {season} {season_average}; national travel
{national_travel_lag1}; exchange rate {usd_cad_rate_lag1}
```

## 4. Manual Validation

I reviewed three summaries against PostgreSQL:

| Month | Actual | Predicted |
|---|---|---|
| January 2025 | 46,221 | 62,469 |
| November 2025 | 44,872 | 52,866 |
| August 2026 | 117,663 | 176,196 |

- Every displayed number matched PostgreSQL.
- Each summary clearly separated the prediction from the actual result.
- The explanations used the supplied historical patterns and did not invent outside causes.
- An initial rounding inconsistency was found (62,468.50 displayed as 62,468) and corrected using round-half-up formatting.

## 5. Cost

A normal 20-summary run is estimated to cost approximately **$0.01**, based on Claude Haiku 5.5 pricing of $0.10 per million input tokens and $0.50 per million output tokens.

## 6. With More Time

I would develop a second model version that adds a same-month-last-year feature and uses more recent training data, then evaluate it on new, unseen months before replacing the current model.
