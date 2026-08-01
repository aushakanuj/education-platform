# Education Agentic Platform Design

This directory contains the evolving design documentation for the platform. Documents move from
high-level product decisions toward detailed component designs, contracts, data models, and
operational concerns.

## Design sequence

1. [Abstract system view](./00-abstract-system-view.md)
2. [Teacher workspace and academic planning](./01-teacher-workspace-and-planning.md)
3. [Assessment blueprints and section variants](./02-assessment-blueprints-and-section-variants.md)
4. [Academic structure, enrollment, and timetable](./03-academic-structure-enrollment-and-timetable.md)
5. [Material lifecycle and AI artifacts](./04-material-lifecycle-and-ai-artifacts.md)
6. [Analytics and comparison insights](./05-analytics-and-comparison-insights.md)
7. [Identity, tenancy, and authorization](./06-identity-tenancy-and-authorization.md)
8. Document ingestion and knowledge indexing
9. AI assistant orchestration
10. Notifications, forums, and certifications
11. API and Flutter client contract
12. Data model and event flows
13. Security, privacy, and auditability
14. Deployment, observability, and disaster recovery

## How to use these documents

Each component document should answer:

- What problem does the component solve?
- Who can use it and what are the authorization boundaries?
- What are the inputs, outputs, states, and failure modes?
- Which workflows and APIs are required?
- What data does it own and what data does it consume?
- How is correctness measured and tested?
- What is included in the POC, and what is deferred?

Decisions should be recorded with their rationale. When a design is uncertain, document the
assumption and the alternative instead of hiding the uncertainty in implementation code.
