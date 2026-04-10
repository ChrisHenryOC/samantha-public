# Plan: Demo Videos via Playwright

Issue: [GH-224](https://github.com/ChrisHenryOC/samantha/issues/224)

## Context

The model selection and skill-based routing work is complete. Qwen2.5 Coder
32B is the recommended production model (99.7% screening accuracy, 20s/step,
20GB). The Phase 8 live system (FastAPI + chat UI) exists but was built before
the skill work — it doesn't use skills and still references Llama 3.1 8B.

These videos will be linked from a Substack article targeting lab informatics
and healthcare IT professionals. The article's central thesis is empirical —
"can local LLMs reliably route lab workflows?" — leading with the 99.7%
Coder 32B result and the hybrid architecture insight.

## Phased Approach

### P0: Article Launch (2 videos)

These two videos ship with the article.

### P1: Follow-Up (2 videos)

Record after article launch based on audience response. If interest is
primarily from lab personnel, prioritize the chat demo. If technical,
prioritize the full workflow path.

### P2: Deferred

Audience-specific demos (pathologist review, persona-specific) — wait for
feedback on what people want to see.

## Framing Guidance

The article avoids the "workflow change is magic" framing. Videos match
this tone:

**Do:**

- Lead with the model's reasoning/explainability — show JSON output,
  applied rules, natural-language explanation
- Show accuracy stats as text overlays ("99.7% across 111 routing steps")
- Show failures honestly — builds more trust than a perfect demo
- Keep it factual: "Here's what the model decided. Here's why. Here's
  where it got it wrong."

**Don't:**

- Frame as "look how easy it is to change workflows"
- Use "seamless," "effortless," "just works"
- Over-polish — a slightly rough research demo is more credible
- Add music or corporate intro/outro

## Step 1: Wire Skills into Live Server

Required for all videos. The live server's `RoutingService.process_event()`
calls `engine.predict_routing()` without `prompt_extras`.

**Changes:**

- `config/server.yaml`: Add `prompt_extras: "skills,retry_clarification"`
  and update `model_id` to `qwen2.5-coder-32b`
- `src/server/app.py`: Read `prompt_extras` from config, pass to
  RoutingService
- `src/server/routing_service.py:89`: Pass `prompt_extras` kwarg to
  `engine.predict_routing()`

## Step 2: Demo Scenarios

### P0 Video 1: Skills-Based Routing in Action (~90 seconds)

Shows accuracy and explainability — the article's headline finding.

Flow:

1. Submit a valid order → routes to ACCEPTED. Show reasoning output.
2. Submit order with fixation_time=5.0h + HER2 → DO_NOT_PROCESS. Show
   model citing ACC-006 and explaining the numeric threshold.
3. Submit order with FNA specimen → DO_NOT_PROCESS. Show model citing
   ACC-004.

Key emphasis: the model's **reasoning text** for each decision. Not just
"it got the right answer" but "it explains why." This is what a rules
engine can't do.

Text overlays: model name (Qwen2.5 Coder 32B), accuracy stats, scenario ID.

### P0 Video 2: Where It Fails — Honest Assessment (~60 seconds)

Shows limitations — the article's credibility differentiator.

Flow:

1. Submit multi-rule scenario (5 simultaneous defects). State routes
   correctly to DO_NOT_PROCESS.
2. Show model's reasoning vs expected rule set. It found 6 rules instead
   of 5 — over-reported.
3. Text overlay: "State routing: correct. Rule citation: incomplete.
   This is why the hybrid architecture matters."

This is the video that separates the article from every vendor demo
showing only the happy path.

### P1 Video 3: Chat Interface — Lab Personnel (~90 seconds)

Combine L1 and L2 from original plan. Show chat interaction:

- "Show me rush orders"
- "Why is ORD-003 on hold?"
- "Mark grossing complete for ORD-007"
- Watch work queue update in real-time

Hold until article response shows whether lab personnel are the
interested audience.

### P1 Video 4: Full Workflow Path (~2 minutes)

Original T1 — walk an order from ACCESSIONING through ORDER_COMPLETE.
Good for deep-dive follow-up or direct lab outreach.

### P2: Deferred

- L3 (Pathologist Review) — too audience-specific for early content
- Additional persona demos — wait for feedback

## Step 3: Playwright Scripts

### Structure (P0 scope)

```text
demos/
  playwright.config.ts     — config: headless=false, video recording on
  scripts/
    p0-routing.ts          — P0 Video 1: routing accuracy + reasoning
    p0-limitations.ts      — P0 Video 2: honest failure assessment
  helpers/
    events.ts              — submit events via API, extract reasoning
    navigation.ts          — select role, wait for load
  videos/                  — output directory for recorded videos
```

P1 scripts added later: `p1-chat.ts`, `p1-full-workflow.ts`

### Playwright Approach

- `page.video()` for recording (built-in, no external tools)
- Slow down interactions with `page.waitForTimeout()` for readability
- Each script self-contained: seeds data if needed, runs demo, stops
- Scripts assume server running on `localhost:8000`
- Research demo feel — not over-polished

### Key Patterns

```typescript
// Submit event via API and show response
const response = await page.evaluate(async () => {
  const res = await fetch('/api/events', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      order_id: 'ORD-DEMO-001',
      event_type: 'order_received',
      event_data: { /* ... */ }
    })
  });
  return res.json();
});
// Display routing decision with reasoning on screen
```

## Step 4: Seed Data (P0 scope)

Only 3 demo orders needed for P0 videos:

- **ORD-DEMO-001**: In ACCESSIONING, valid order (routes to ACCEPTED)
- **ORD-DEMO-002**: In ACCESSIONING, fixation_time=5.0h with HER2
  (triggers ACC-006 → DO_NOT_PROCESS)
- **ORD-DEMO-003**: In ACCESSIONING, 5 simultaneous defects (multi-rule
  scenario for limitations video)

## Files to Create/Modify

| File | Change | Phase |
|------|--------|-------|
| `config/server.yaml` | Update model_id, add prompt_extras | Step 1 |
| `src/server/app.py` | Read prompt_extras from config | Step 1 |
| `src/server/routing_service.py` | Pass prompt_extras to predict_routing | Step 1 |
| `src/server/seed.py` | Add 3 demo-specific orders | P0 |
| `demos/playwright.config.ts` | NEW — Playwright config with video | P0 |
| `demos/scripts/p0-*.ts` | NEW — 2 P0 demo scripts | P0 |
| `demos/helpers/*.ts` | NEW — shared helpers | P0 |
| `demos/scripts/p1-*.ts` | NEW — 2 P1 demo scripts | P1 |

## Prerequisites

- llama-server running with Qwen2.5 Coder 32B loaded
- Live server running: `./scripts/start_server.sh`
- Playwright installed: `npx playwright install chromium`
- Node.js for Playwright scripts

## Implementation Order

1. Wire skills into live server (config + 2 code files)
2. Add 3 demo seed orders
3. Create Playwright helpers and config
4. Write P0 scripts (routing + limitations)
5. Record, review, iterate on timing
6. (After article launch) Write P1 scripts based on response

## Verification

1. Server starts with skills enabled (health endpoint shows Coder 32B)
2. Submit test event via API — verify skill-based routing + reasoning
3. Run P0 Playwright scripts — verify video output
4. Review videos: timing, readability, reasoning visible, stats overlaid
