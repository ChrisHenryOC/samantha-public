# Feedback on Demo Video Plan (demo-plan.md)

**From:** Article project (gtan-samantha)
**Date:** 2026-03-28
**Context:** These videos will be linked from a Substack article targeting lab informatics / healthcare IT professionals. The article's central thesis is empirical — "can local LLMs reliably route lab workflows?" — not a product pitch about workflow adaptability. The article leads with the 99.7% Coder 32B result, the hybrid architecture insight (38/40 rules are deterministic), and model selection findings.

---

## Overall Assessment

The plan is well-structured and the two-audience approach (technical vs. lab personnel) is smart. The Playwright approach makes sense for repeatability. The Step 1 work (wiring skills into the live server) is required regardless and should proceed as planned.

**Main concern:** The current 6-video scope is too broad for the initial launch. Recommend a phased approach — 2 videos for the article launch, remaining 4 as follow-up content.

---

## Priority Recommendations

### P0: Record These Two for the Article Launch

**Video 1: Skills-Based Routing in Action (~90 seconds)**

Map to existing plan: This is a tighter version of T2 (Accessioning Validation). Focus on what makes the article's thesis tangible — the model reading skill documents, making routing decisions, and showing its reasoning.

Suggested flow:
- Submit a valid order → routes to ACCEPTED. Show the reasoning output.
- Submit an order with fixation_time=5.0h + HER2 → DO_NOT_PROCESS. Show the model citing ACC-006 and explaining the numeric threshold.
- Submit an order with FNA specimen → DO_NOT_PROCESS. Show the model citing ACC-004.
- Key emphasis: the model's **reasoning text** for each decision. This is the differentiator — not just "it got the right answer" but "it explains why."

Why this video: The article's headline finding is accuracy. This video shows accuracy in action with explainability — the thing a rules engine can't do.

**Video 2: Where It Fails — Honest Assessment (~60 seconds)**

Map to existing plan: This is T3 (Known Limitations), slightly reframed.

Suggested flow:
- Submit the multi-rule scenario (5 simultaneous defects). State routes correctly, but the model over-reports rules.
- Show the model's reasoning vs. the expected rule set. Point out where it satisficed.
- Brief text overlay or narration: "State routing: correct. Rule citation: incomplete. This is why the hybrid architecture matters."

Why this video: The article's credibility comes from honesty about failure modes. Showing limitations on video — not just describing them in text — dramatically increases trust with a technical lab informatics audience. This is the video that separates you from every vendor demo that only shows the happy path.

### P1: Record After Article Launch (Based on Response)

**Video 3: Chat Interface — Lab Personnel Perspective (~90 seconds)**

Combine L1 and L2. Show the chat interaction: "Show me rush orders," "Why is ORD-003 on hold?", "Mark grossing complete for ORD-007." This demonstrates the user experience layer that lab directors and techs would interact with.

Hold this until you see whether the article generates interest from lab personnel (vs. technical/informatics people). If the interest is primarily technical, this video may not be the right next step.

**Video 4: Full Workflow Path (~2 minutes)**

This is T1 as planned. Good for a deep-dive follow-up or for direct outreach to specific labs where you want to show the complete system.

### P2: Defer

- L3 (Pathologist Review) — too audience-specific for early content
- Additional persona-specific demos — wait for customer feedback on what they want to see

---

## Framing Guidance for Video Content

The article avoids the "workflow change is magic" framing that every LIS vendor uses. The videos should match this tone:

**Do:**
- Lead with the model's reasoning/explainability — show the JSON output, the applied rules, the natural-language explanation
- Show the numbers — overlay accuracy stats contextually ("99.7% across 111 routing steps")
- Show the failure honestly — this builds more trust than a perfect demo
- Keep it factual: "Here's what the model decided. Here's why. Here's where it got it wrong."

**Don't:**
- Frame it as "look how easy it is to change workflows" — even if it's true, this claim has been burned by vendors
- Use phrases like "seamless," "effortless," "just works" — lab informatics people are allergic to these
- Over-polish — a slightly rough research demo is more credible than a slick product video for this audience
- Add music or corporate intro/outro — this is a research project, not a product launch

---

## Technical Notes

- The plan's Playwright approach is good for repeatability if you plan to re-record as the system evolves. For the initial 2 videos, screen recording (OBS or macOS) with light editing would also work and might feel more natural.
- The seed data plan (Step 4) is solid. For P0 videos, ORD-DEMO-001, ORD-DEMO-002, and the multi-rule scenario data are sufficient.
- Consider adding brief text overlays (model name, accuracy stats, scenario ID) rather than voice narration for the first pass. Text overlays are faster to produce and easier to update when results change.
