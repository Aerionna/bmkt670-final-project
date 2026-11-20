# Dashboard Notes (Draft)

## 1. Audience and Decision

- **User:** The CEO of a Montana destination organization.
- **Decision:** Whether to increase, maintain or reduce destination marketing aimed at Canadian travelers for an upcoming month, based on predicted inbound passenger crossings.
- **Important:** Crossings count inbound personal-vehicle passengers at Montana's Canadian ports. They indicate travel demand; they are not a confirmed count of Canadian tourists.

## 2. Questions Answered

| Page | Question | Status |
|---|---|---|
| 1 | How have inbound passenger crossings at Montana's Canadian border changed over time and by season? | Built |
| 2 | How accurately does the model predict monthly crossings, and when are its predictions least reliable? | Built |
| 3 | Based on predicted border traffic, should the organization adjust marketing aimed at Canadian travelers? | Built |
| 4 | How do border-crossing patterns differ among Montana's ports of entry? | Built |

## 3. AI Feature

`ai/generate_summaries.py` uses `claude-haiku-5-5` to write a two-sentence summary of each test prediction. The summaries are saved in PostgreSQL (`ai_summaries`), and Page 3 of the dashboard displays the saved text without making new API calls. Before saving, the script checks each reply's length and that every number comes from the supplied facts.

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

## 4. Manual Validation and Prompt Refinement

I reviewed the following three summaries against their PostgreSQL records:

- **January 2025:** “For January 2025, the model predicted 62,469 inbound personal-vehicle passengers crossing from Canada into Montana, but 46,221 actually crossed, so the prediction was too high. The actual count was close to the historical training data average for January of 47,258, which suggests the model may have leaned toward the higher recent months.”

- **November 2025:** “The model predicted 52,866 inbound personal-vehicle passenger crossings from Canada into Montana for November 2025, but 44,872 were recorded, so the prediction was too high. The actual November count falls below the historical training data average for November of 56,284, which suggests this November may have run weaker than typical Novembers.”

- **August 2026:** “The model predicted 176,196 inbound personal-vehicle passengers crossing from Canada into Montana in August 2026, but 117,663 actually crossed, so the prediction was too high. August crossings appear to have run well below the historical training data average for August of 163,064, which may explain much of the miss.”

The prompt was refined three times. The first version accurately repeated the prediction and actual result but did not meaningfully explain the miss. The second added historical context but often listed too many factors, making the summaries long and difficult to scan. The final version requires exactly two sentences under 55 words and one cautious, evidence-based explanation. I confirmed that the displayed numbers matched PostgreSQL, the summaries did not invent outside causes and predictions were clearly separated from actual results. I also corrected a rounding inconsistency by applying round-half-up formatting throughout the script and dashboard.

## 5. Cost

A normal 20-summary run costs an estimated **$0.01**, based on Claude Haiku 5.5 pricing of $0.10 per million input tokens and $0.50 per million output tokens.

## 6. With More Time

I would develop a second model version that adds a same-month-last-year feature and uses more recent training data, then evaluate it on new, unseen months before replacing the current model.
