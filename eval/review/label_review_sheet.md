# Label Review Sheet

**Agreement summary:** Labeller A (AI/Claude) and Labeller B (AI/independent) agree on **43 of 44** answerable TEST items (**97.73% raw agreement, Cohen's κ = 0.95**). There is **1 disagreement** to adjudicate. No items are marked low-confidence by Labeller B.

**How to use this sheet:** Read Section 1 and fill in "Your verdict" for the one disagreeing item. Section 2 is empty (no low-confidence agreements). Section 3 lists all 43 agreed items for quick reference. When done, return this file to the coding agent to compute final human-adjudicated accuracy.

---

## Section 1: Disagreements (judge these)

### Q036 — multi_passage

**Question:**
What pushed logging firms near Boumba Bek to cut back operations, and what commitments did they make at the 2024 private sector workshop?

**Gold quote(s):**

> (1) "operations have been scaling down (SIM has closed) due to high taxation, leading to job losses, increased forest pressure and suspension of company-financed ecoguard patrols"

> (2) "Logging companies pledged to combat ivory poaching and other illegal activities in their concessions, livelihood projects in collaboration with IP&LCs, and committed to sustainable forest management practices"

**Model reply (full text):**

> Based on the provided excerpts, logging companies were concerned about high taxes paid, which may force closure if no remedial actions are taken (and operations have been scaling down due to high taxation).
>
> At the 2024 private sector workshop, logging companies made the following commitments:
> - They pledged to combat ivory poaching and other illegal activities in their concessions.
> - They pledged livelihood projects in collaboration with IP&LCs.
> - They committed to sustainable forest management practices.

**Labeller A (other AI):** `correct`
- Note: *(empty)*

**Labeller B (independent):** `partial` (confidence: high)
- Reason: Reply mentions high taxation and scaling down but omits 'SIM has closed', job losses, forest pressure, and suspended ecoguard patrols. No contradictions.

Your verdict: partial  (correct / partial / wrong / refused)

Rationale (project owner): judged from the gold quote vs the reply. Part 2 (workshop commitments) is fully covered; part 1 omits SIM closure, job losses, forest pressure and suspended ecoguard patrols.

---

## Section 2: Agreed but low confidence (please glance)

*No items in this section — all agreements are high-confidence.*

---

## Section 3: Agreed, high confidence

| qid  | type             | label   |
|------|------------------|---------|
| Q001 | single_fact      | correct |
| Q002 | single_fact      | correct |
| Q003 | single_fact      | correct |
| Q004 | single_fact      | correct |
| Q006 | single_fact      | correct |
| Q009 | single_fact      | correct |
| Q010 | single_fact      | correct |
| Q011 | single_fact      | correct |
| Q012 | single_fact      | refused |
| Q014 | single_fact      | correct |
| Q015 | single_fact      | correct |
| Q016 | single_fact      | correct |
| Q018 | single_fact      | correct |
| Q019 | single_fact      | correct |
| Q020 | single_fact      | refused |
| Q021 | numbers_tables   | correct |
| Q024 | numbers_tables   | wrong   |
| Q025 | numbers_tables   | correct |
| Q026 | numbers_tables   | correct |
| Q027 | numbers_tables   | correct |
| Q028 | numbers_tables   | refused |
| Q029 | numbers_tables   | correct |
| Q030 | numbers_tables   | correct |
| Q031 | numbers_tables   | correct |
| Q033 | numbers_tables   | correct |
| Q034 | numbers_tables   | correct |
| Q035 | multi_passage    | correct |
| Q038 | multi_passage    | correct |
| Q039 | multi_passage    | partial |
| Q040 | multi_passage    | refused |
| Q042 | multi_passage    | correct |
| Q045 | multi_passage    | correct |
| Q046 | multi_passage    | correct |
| Q047 | cross_document   | correct |
| Q049 | cross_document   | correct |
| Q050 | cross_document   | refused |
| Q051 | cross_document   | correct |
| Q053 | cross_document   | partial |
| Q055 | cross_document   | partial |
| Q056 | cross_document   | partial |
| Q057 | cross_document   | partial |
| Q058 | cross_document   | refused |
| Q060 | cross_document   | correct |

---

**Instructions:** Fill "Your verdict" for every item in Section 1 (and Section 2 if any items were present). Then give this file back to the coding agent to compute final human-adjudicated accuracy.
