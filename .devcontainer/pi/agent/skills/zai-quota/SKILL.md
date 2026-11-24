---
name: zai-quota
description: Check Z.ai GLM Coding Plan quota, credit windows, per-model or per-tool usage, and reset times by running the zai-quota helper. Use when the user asks about quota, remaining credits, usage stats, plan limits, or when deciding if budget exists for expensive Z.ai calls.
---

# zai-quota helper

Run `zai-quota` (on PATH; installed at `~/.pi/agent/bin/zai-quota`, which is
bind-mounted to `/workspace/headunit/.pi/agent/bin/zai-quota`). It is a plain
python3 script with no dependencies beyond the stdlib.

| Command | Shows |
|---|---|
| `zai-quota` | 5-hour and weekly credit windows: used / limit, %, remaining, reset time |
| `zai-quota --json` | Raw `quota/limit` response |
| `zai-quota --models` | Per-model token usage for the last 24h (hourly buckets; see `modelSummaryList` for totals) |
| `zai-quota --tools` | Per-MCP-tool usage for the last 24h |
| `zai-quota --hours N` | Widen the `--models` / `--tools` window |
| `zai-quota --help` | Usage |

Notes:

- All times are rendered in **Australia/Melbourne** (operator's local time);
  override with `ZAI_TZ=UTC` etc. Include the zone abbreviation when reporting.
- The API key comes from `~/.pi/agent/auth.json` (`zai` entry) or
  `Z_AI_API_KEY`. Never print the key or echo it into output.
- These checks are read-only GETs against
  `api.z.ai/api/monitor/usage/*` — they do **not** consume plan credits.
- The endpoints are undocumented and may change without notice. On unexpected
  errors, show the raw message and stop; do not improvise around the API.
- Quota interpretation: in the JSON, `usage` is the window *limit*,
  `currentValue` is what was consumed, `unit` 3 = hours, 6 = weeks.
- Peak window line: Mon–Fri 14:00–18:00 UTC+8 (= 17:00–21:00 Melbourne AEDT,
  16:00–20:00 AEST). Peak burns credits at the full rate; off-peak gets a
  flat 50% discount for all models (per z.ai documentation). When
  scheduling heavy batch work for the operator, prefer off-peak windows.
- If a session is about to make many paid Z.ai calls (MCP tools, vision,
  image work), it is reasonable to run `zai-quota` first and mention the
  remaining budget in the 5-hour window.
