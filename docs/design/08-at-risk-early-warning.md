# At-Risk Early Warning

## 1. Scope

This component turns `student_360` marks and attendance into a teacher/administrator-facing flag
that a specific student needs attention, with the reasoning attached. It is a **policy document**:
what counts as at-risk, who sees a flag, what triggers one, and what the system must never do
without a person. It does not specify the scoring implementation — that is a separate build task, owned by the
engine's author, built to the requirements below.

It governs the successor to two interim placeholders already live in the teacher UI (§10), and is
written in response to the 19 Aug 2026 mentor review, which named this the priority gap once basic
scaffolding was demonstrated.

This document does not replace [Analytics and comparison insights](./06-analytics-and-comparison-insights.md).
§3 below states exactly how the two relate — they are not the same feature.

## 2. Decisions

| Decision | Choice | Rationale |
| --- | --- | --- |
| Form | Rule-based on marks + attendance, not ML | Matches the signed charter; explainable without 2-3 cohorts of historical outcome data the sponsor was never able to confirm |
| Relationship to struggle flags | A separate roll-up that *consumes* §4.3's struggle/mastery signals plus attendance; does not replace them | Keeps the per-subtopic diagnostic (student-facing) distinct from the whole-student early warning (staff-facing) — see §3 |
| Signal grain | Mastery is evaluated per subject offering; attendance is evaluated per student per academic period, because `student_360.attendance_percent` is not tracked per subject | Matches the data as it actually exists; a rule that assumes per-subject attendance will be wrong by construction |
| Numeric thresholds | Not fixed in this document | Calibrated against the school's real distribution and validated against the named test cases in §6.3 — inventing a number here repeats the exact mistake this document exists to correct |
| Flag visibility | The student's assigned teacher(s) and the institution's administrators, through the existing `Scope` — never a new access path | Reuses [Identity, tenancy, and authorization](./02-identity-tenancy-and-authorization.md) rather than a second permission implementation (Rule 7) |
| Shown to the student directly? | No — not as an "at-risk" label | An actionable staff-facing flag is a different thing from the student-facing struggle chips in §4.3 of doc 06; see §7.3 |
| Automated action | None. A flag is a suggestion in a teacher-facing list, always dismissible, and every dismissal is audited | Matches the charter's "a human teacher always makes the final call" |
| Predictive claims | None, ever, in any report or presentation | All data is synthetic (see `backend/src/education_platform/modules/synthetic/generator.py`) — thresholds tuned on it prove the mechanism works, not that it predicts real outcomes |

## 3. This is not the same feature as "struggle flags"

[Analytics and comparison insights](./06-analytics-and-comparison-insights.md) §4.3 already defines
a **struggle flag**: a per-subtopic, quiz-outcome-derived signal, visible to both the student (as a
dashboard chip) and the teacher (as a class-level weak-outcome list). That system is not touched by
this document and should not be rebuilt.

**At-risk early warning is a different, higher-stakes thing sitting on top of it:** a whole-student
roll-up across *all* of a student's subject signals plus attendance, meant to prompt a teacher to
look at a specific child, not to inform the child directly about one weak subtopic. Conflating the
two was a live risk — the mentor's note about "granular subtopic tagging" and the charter's
"early-warning engine" describe two different consumers of the same underlying data, and this
document only owns the second one.

```text
question_outcome_tags / learning_outcomes  →  struggle flag (doc 06 §4.3, per-subtopic, shown to student)
                                            ↘
student_360 (mastery_percent, attendance_percent)  →  AT-RISK FLAG (this document, per-student, shown to staff)
```

## 4. Signal inputs

Every input comes from `student_360` (the same register every other analytics feature reads — doc 02
§11a.1's "one resolver, no hand-written checks" principle applies here too: no separate query path).

| Signal | Column | Grain |
| --- | --- | --- |
| Subject mastery | `mastery_percent` | Per student, per subject offering |
| Quiz engagement | `quizzes_taken`, `last_attempt_at` | Per student, per subject offering |
| Attendance | `attendance_percent` | Per student, per academic period (whole-student — see §2) |
| Trend | Same columns, read across two points in time | The single most requested addition from the 19 Aug review: a flat 56% is a different situation from a 74%-to-38% slide, and the rule must be able to tell them apart, not just threshold the latest number |

If subtopic-level struggle data (doc 06 §4.3) is already computed and queryable at the time this is
implemented, it may be added as a fourth input — a student failing the same outcome repeatedly is a
sharper signal than a subject average. This is additive, not required for a first version.

## 5. What a flag must contain

Modelled on doc 06 §5's `EvaluationSnapshot`, because the same discipline applies: a flag with no
audit trail is not distinguishable from a guess.

```text
AtRiskFlag
├── student_id
├── grade_subject_offering_id      (null for an attendance-only flag — see §7.2)
├── academic_period_id
├── tier                            (names and count are the engine author's call, within §6)
├── drivers[]                       — every signal that fired, each naming:
│     ├── metric                    (e.g. "mastery_percent", "attendance_percent")
│     ├── value                     (the actual number, at the time of computation)
│     ├── comparison                (the threshold or trend condition it failed)
│     └── window                    (single reading vs. N-attempt trend)
├── computed_at
├── status                          (active / dismissed / resolved)
├── dismissed_by, dismissed_at, dismissal_note   (null unless dismissed)
```

**AR-1.** A flag with an empty `drivers[]` must not exist. If nothing can be named as the reason, no
flag is raised — this is the direct implementation of "predictions explain themselves."

## 6. Rule framework

### 6.1 What this document fixes

- Signals are read from `student_360` only (§4).
- A flag names its drivers explicitly (§5, AR-1).
- Mastery and attendance are evaluated separately per §2's signal-grain decision — a rule may not
  average them into one blended score, because averaging is exactly what would hide "strong
  everywhere except Maths" inside a merely-below-average composite.
- Both a **level** condition (is the current number low) and a **trend** condition (is it declining)
  must be checked. Level alone would flag a consistently-average-but-stable student the same as one
  in freefall; trend alone would miss a student who has been quietly struggling all term.

### 6.2 What this document deliberately leaves open

The exact cut points (what mastery percent, what attendance percent, how many points of decline over
how many attempts) are **not specified here**. Per §2, picking them without evidence is the
placeholder mistake repeated. The recommended calibration method, for whoever builds this:

1. Run the candidate rule against the synthetic school's actual distribution and report how many
   students it flags — neither near-zero nor a large fraction of the school is a usable result.
2. Validate against the named cases in §6.3 before validating against anything else.
3. State the chosen numbers and *why* those numbers, in the same document or its implementation PR —
   an unexplained constant is indistinguishable from a guess to the next person reading the code.

### 6.3 Cases any implementation must get right

These exist in the synthetic school precisely to test this (`modules/synthetic/generator.py`):

| Case | Student | Must produce |
| --- | --- | --- |
| Subject-specific, not global | Aisha Rahman (S-00097): 56% Maths mastery, 61–77% in four other subjects, 62% attendance | A flag whose drivers name Mathematics specifically — not a generic "struggling student" flag that reads the same as a child weak everywhere |
| Attendance-only | Any student below the attendance line but with mastery at or above the school median in every subject | A flag driven by attendance alone, with no subject named as a mastery driver |
| Decline without a low absolute score | A student whose average is still nominally fine but has slid several points across recent attempts | A flag from the trend condition (§6.1), proving level-only thresholds are insufficient |
| Section-level pattern, not a single flag | Grade 8 Mathematics Section A vs Section B (planted gap) | This is a *cohort* signal, not an individual one — confirm the rule does not misfire into flagging every Section A student individually when the real story is a teaching or content gap. Out of scope for this document to resolve, but the engine must not silently paper over it either |

## 7. Visibility and authorization

### 7.1 Reuse, don't reimplement

A flag is read exactly like any other row in `student_360`: through `scope_predicate_for` with a
`ScopeColumns` mapping for wherever flags end up stored, reusing doc 02 §11a.1's principle and the
module built for exactly this reuse in
[authorization/predicate.py](../../backend/src/education_platform/modules/authorization/predicate.py).
There is no reason for this feature to need its own access check, and every reason it must not have
one — that is precisely how the PR #119 tenancy leak happened.

### 7.2 Who sees which flag

- A **subject-driven** flag (mastery, or mastery+attendance together) is visible to the teacher(s)
  who teach that student in that subject, and to the institution's administrators.
- An **attendance-only** flag has no single owning subject teacher — attendance is a whole-student
  concern, and the permission model's teacher reach is deliberately scoped to (offering, section)
  pairs (doc 02 §11a.2), not "every teacher of this child." Routing it to **administrators only** is
  the recommended default: it avoids inventing a new "all of this student's teachers" broadcast the
  access model doesn't otherwise have, and matches how a school would typically triage an attendance
  concern (through a homeroom or admin function) rather than a single subject teacher.

### 7.3 Never shown to the student as a label

Doc 06 §7.1 already shows a student their own struggle chips and mastery — that stands. This
document's flag is a different object: a staff-facing prompt to look at a child, not a
student-facing evaluation. Labelling a child "at risk" and showing them that label directly is a
different, harder decision than showing them their own weak subtopic, and this document does not
make that call — it defaults to **no**, staff-only, and treats otherwise as an open decision (§14).

## 8. Human-in-the-loop requirements

**AR-2.** No message, notification, or communication to a student, parent, or guardian is ever
triggered automatically by a flag. (No parent role exists in the built system today — see doc 02
§12 — so this is currently moot in practice, but the rule holds regardless of whether that changes.)

**AR-3.** No flag writes to, or otherwise affects, any academic record, grade, or permanent file. A
flag is visible only in the teacher/administrator-facing early-warning view.

**AR-4.** A teacher or administrator can dismiss a flag. Dismissal requires no justification beyond
the optional note in `dismissal_note`, but the action itself — who, when, which flag — is written to
the audit log exactly as any other sensitive action is (doc 02 §10). A pattern of dismissals is
useful evidence for whether the rule is well-calibrated; that evidence only exists if dismissal is
logged.

**AR-5.** Every flag view is a scoped, audited read, same as any other `student_360`-derived access
(doc 02 §11a.4). A flag that was computed but never actually shown to anyone is not itself sensitive;
a flag that was *viewed* is exactly the kind of event Rule 5 exists to capture.

## 9. Binding requirements summary

| ID | Requirement |
| --- | --- |
| AR-1 | A flag with no named drivers must not exist |
| AR-2 | No automated communication to a student or guardian |
| AR-3 | No automated write to any academic record |
| AR-4 | Dismissal is a first-class, audited action |
| AR-5 | Flag views are scoped and audited like any other analytics read |

## 10. Retiring the interim placeholders

Two placeholders shipped in PR #119, deliberately as stand-ins, and both are named here so whoever
implements this knows exactly what to remove rather than leave running alongside the real engine
(the two-implementations failure this whole document exists to prevent, per doc 02 §11a.1):

- `ATTENDANCE_THRESHOLD = 75` in `frontend/src/pages/teacher/RosterPage.tsx` — the roster's "worth a
  look" count.
- `MASTERY_CONCERN = 60` in `frontend/src/pages/teacher/StudentPage.tsx`, plus the adjacent
  `attemptTrend()` last-3-vs-earlier, 5-point-margin banner.

Neither was derived from anything — both were picked for demo plausibility. Worth noting: `60` does
not even match doc 06 §6's own already-agreed institution default mastery threshold of `70%`, which
is a small, concrete illustration of exactly the drift two competing numbers produce.

## 11. Test matrix

To be implemented alongside the engine, in the style of doc 02 §11a.5's table.

| ID | Rule | Expected |
| --- | --- | --- |
| T-AR-01 | Aisha Rahman case (§6.3) | Flag names Mathematics specifically, not a generic low-performer flag |
| T-AR-02 | Attendance-only case (§6.3) | Flag has an attendance driver and no mastery driver |
| T-AR-03 | Decline-without-low-absolute case (§6.3) | Flag exists and its driver cites the trend, not a level threshold |
| T-AR-04 | A student above every threshold, flat trend | No flag |
| T-AR-05 | Teacher not assigned to the student's offering | Cannot see the flag — zero rows, not 403 (doc 02 §11a.3) |
| T-AR-06 | Attendance-only flag, any teacher | Not visible to a subject teacher who isn't an administrator (§7.2) |
| T-AR-07 | Dismiss a flag | Written to the audit log with actor, timestamp, and flag id (AR-4) |
| T-AR-08 | View a flag | Written to the audit log like any other scoped read (AR-5) |
| T-AR-09 | Flag with an empty driver list | Cannot be constructed — enforced at the type/validation level (AR-1) |
| T-AR-10 | Cross-tenant | An administrator at a second institution cannot see the first institution's flags — the standard this project now holds every new feature to |

## 12. POC acceptance criteria

1. Flags are computed only from `student_360` columns, never a second data path.
2. Every flag names at least one driver with its actual value and the condition it failed.
3. A flag is visible only to the student's assigned teacher (subject-driven) or administrators
   (attendance-only or subject-driven), through the existing `Scope`.
4. No flag is visible to the student it concerns, or to any account outside the resolving `Scope`.
5. No automated action of any kind follows from a flag being raised.
6. Dismissing or viewing a flag produces an audit entry.
7. The three named cases in §6.3 behave as specified.
8. Both placeholder thresholds named in §10 are removed in the same change that ships this.

## 13. Deferred scope

- Machine-learned scoring of any kind — explicitly excluded by the charter, not just postponed.
- Parent-facing visibility of flags — blocked on the parent role itself being out of POC scope
  (doc 02 §12).
- Automated interventions, messages, or referrals of any kind (AR-2, AR-3) — always a person's
  decision, not a future automation target.
- Section- or cohort-level flagging (the Grade 8 Maths A/B case in §6.3) — named as a case the engine
  must not mishandle, not a feature this document specifies.
- Cross-subject "all of this student's teachers" visibility — the attendance-only routing in §7.2 is
  the deliberately simpler default for the POC.

## 14. Open decisions

- Should an attendance-only flag ever reach a subject teacher, not just administrators — e.g. if a
  homeroom-style role doesn't exist in this school model? §7.2's default is administrators-only;
  this needs a real answer if the POC demo wants to show a teacher acting on an attendance concern.
- Should a dismissed flag be able to re-fire on the same underlying condition, or does dismissal
  suppress it until the underlying numbers change materially? Not specified above.
- Exact tier count and naming (§5) — left to the engine's author, but worth a second opinion before
  it reaches the sponsor demo, since tier *names* are themselves a communication choice about a
  child.
