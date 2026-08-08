# Analytics and Comparison Insights

## 1. Scope

This component turns StudentLearningDirectory progress, common mastery quiz attempts, and
question-level outcome tags into evidence-based evaluation views for students and teachers.

It implements four metric families for the student-evaluation POC:

1. marks and assessment history;
2. anonymized peer comparison context;
3. subtopic / learning-outcome mastery and struggle signals;
4. time-series progress for score, mastery, and completion.

Each scored released attempt writes a versioned **EvaluationSnapshot** into the student's private
directory. Learner presentation is defined in
[Student learning experience](./01-student-learning-experience.md). Assessment evidence production
is defined in
[Assessment](./05-assessment-common-subtopic-mastery-quizzes.md).

The component does not rank students by default, expose classmate identities, or change
SourceCurriculum records.

## 2. Decisions

| Decision | Choice | Rationale |
| --- | --- | --- |
| Primary evidence | Online objective common-mastery attempts with question- and outcome-level scores | Enables valid struggle analysis and learner dashboards. |
| Snapshot unit | One EvaluationSnapshot per scored released attempt | Keeps student directories auditable and versioned. |
| Mastery threshold | Institution-configured default | Provides consistent evaluation across the common cohort. |
| Minimum peer evidence | At least 5 scored students and 80% completion in the comparison cohort | Avoids over-interpreting small or incomplete samples. |
| Peer presentation | Anonymized percentile band or cohort band; never names or raw peer marks | Protects student privacy. |
| Peer cohort | Same Grade–Subject–Subtopic common mastery quiz version | Matches the common curriculum model. |
| Teacher comparison audience | Assigned teacher only | Group performance remains private during the POC. |
| AI action | Not required for the evaluation POC | The four pillars are deterministic. |
| Curriculum mutation | Evaluation never edits SourceCurriculum | Preserves common cohort content. |

## 3. Evidence model

| Type | Definition | Example |
| --- | --- | --- |
| Source fact | An immutable recorded event or value | Asha scored 21/30 on Linear Equations mastery quiz v1 attempt 1. |
| Calculated metric | A deterministic calculation from source facts | Outcome “inverse operations” correctness: 40%. |
| Comparison | A calculated relationship to an eligible cohort | Asha is in the middle 50% of Grade 8 Mathematics for this quiz version. |

The evaluation POC displays source facts, calculated metrics, and comparisons. AI interpretations
and remediation drafts are deferred.

## 4. Metric families

### 4.1 Marks and assessment history

| Metric | Definition |
| --- | --- |
| Attempt score | Valid marks earned on a scored attempt |
| Score percent | Attempt score divided by maximum marks |
| Pass status | Whether score meets institution pass threshold |
| Mastery status | Whether score meets active mastery threshold |
| Attempt history | Ordered list of released attempts for a subtopic quiz |
| Subject average | Mean of latest released subtopic scores in a subject |
| Completion rate | Scored students divided by enrolled Grade–Subject students for a quiz |

### 4.2 Anonymized peer comparison

Eligible when comparing a learner against a cohort that shares:

```text
Academic period
+ Grade
+ Subject
+ Topic
+ Subtopic
+ Common mastery quiz version
```

| Metric | Definition |
| --- | --- |
| Cohort size | Count of scored eligible attempts in the peer set |
| Percentile band | Learner position expressed as a band, e.g. top 25%, middle 50%, bottom 25% |
| Cohort range | Cohort median and interquartile range, without identities |
| Cohort delta | Teacher-only difference between assigned reporting groups on the same quiz |

If either condition fails:

```text
marked_students >= 5
AND
marked_students / enrolled_students_at_assessment >= 0.80
```

the platform returns insufficient evidence and suppresses peer conclusions. Personal marks and
subtopic metrics remain visible.

### 4.3 Subtopic mastery and struggle

Derived only from question-level outcome tags on scored online common-mastery attempts.

| Metric | Definition |
| --- | --- |
| Outcome score | Correct marks for questions tagged with the outcome divided by available marks for that outcome |
| Outcome mastery | Outcome score meets the mastery threshold |
| Struggle flag | Outcome score below struggle threshold on the latest attempt, or across the last N attempts |
| Common class struggles | Teacher-facing ranked outcomes with lowest class outcome scores |

Default POC struggle threshold: below 50% on an outcome with at least two tagged questions in the
attempt evidence set.

Manual total-mark-only entries cannot produce struggle flags.

### 4.4 Time-series progress

| Metric | Definition |
| --- | --- |
| Score trend | Sequence of released attempt percentages over time for a topic or subject |
| Mastery trend | Sequence of mastery statuses or mastery rates over successive subtopic quizzes |
| Completion trend | Material completion and quiz completion over weeks |
| Retake delta | Change between attempt N and attempt N+1 on the same quiz version |

## 5. Evaluation snapshot

```text
EvaluationSnapshot
├── student_id
├── academic_period_id
├── grade_subject_offering_id
├── topic_id
├── subtopic_id
├── quiz_version_id
├── attempt_id
├── metric_version
├── marks_block
├── peer_block (or insufficient_evidence)
├── outcome_block
├── trend_block
└── created_at
```

Snapshots are immutable. Corrections create a new snapshot linked to the corrected attempt and
invalidate or supersede the prior snapshot for display.

## 6. Mastery thresholds

```text
Institution default mastery threshold: 70%
Institution default pass threshold: 50%
```

The POC uses the institution default for every common mastery quiz. Scoped teacher overrides are
deferred.

## 7. Role views

### 7.1 Student view

Shows own:

- marks and attempt history;
- anonymized peer band or insufficient-evidence state;
- subtopic mastery and struggle chips;
- time-series progress.

Never shows classmate names, identifiable ranks, or other students' answers.

### 7.2 Teacher view

Shows for assigned groups:

- class completion, mean/median, distribution, mastery/pass rates;
- common weak outcomes;
- trends across successive subtopic quizzes;
- individual student result drill-down for assigned students;
- cohort comparison only when the teacher is assigned to both compared groups and evidence rules
  pass.

## 8. Authorization and privacy

- A student sees only own metrics and anonymized peer bands.
- A teacher sees only facts, metrics, and comparisons for active teaching assignments.
- Every calculation input and metric version is auditable.
- Evaluation evidence must not mutate SourceCurriculum materials or quizzes.

## 9. Failure handling

| Condition | System behavior |
| --- | --- |
| Insufficient scored students | Show personal or standalone metrics; suppress peer conclusion. |
| Completion below 80% | Show standalone metrics; explain missing-submission rate. |
| Quiz version mismatch | Block comparison and identify incompatible quiz versions. |
| No question-level data | Allow marks/history metrics; mark subtopic analysis unavailable. |
| Invalid or corrected attempt | Recalculate dependent snapshots after correction resolves. |

## 10. POC acceptance criteria

1. The platform calculates marks history from scored online common-mastery attempts.
2. Each scored released attempt creates a versioned EvaluationSnapshot in the student directory.
3. Peer context is anonymized and suppressed when evidence thresholds fail.
4. Subtopic struggle analysis uses learning-outcome tags from question-level results.
5. Time-series views show score, mastery, and completion across released subtopic attempts.
6. Students see own dashboards and teachers see assigned groups.
7. Teacher cohort comparison requires matching quiz version and evidence thresholds.
8. The four evaluation pillars never alter or personalize the SourceCurriculum.
9. Facts and calculated metrics remain visually and structurally distinct.

## 11. Deferred scope

- Predictive models and causal impact claims
- Formal psychometric calibration and IRT
- Parent progress views, AI interpretations, and remediation recommendations
- Private dynamic-material generation inputs beyond the evaluation snapshot contract
- Adaptive-practice analytics separated from mastery peer cohorts
- Teacher threshold overrides

## 12. Open decisions

- Should peer context show percentile, fixed performance bands, or both by default?
- Which score bands should institutions use for distributions?
- How long after a mark correction should metrics be recalculated?
