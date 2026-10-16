**Project Weekly Catch-up — Minutes of Meeting (MoM)**

**Meeting Details**

* **Date & Time:** August 19, 2026 | 2:35 PM IST


* **Duration:** ~49 minutes


* **Attendees:** Peeyush (Project Mentor/Reviewer), tanmay, Aushak Anuj Dendukuri, Suparna Dhumale, Pranit Daggupati, Rahul Vamshikanth Gunda




---

**Executive Summary**
The team demonstrated the functional end-to-end platform scaffolding, covering student, teacher, and admin workflows. The review validated the architectural pipeline, guardrails, and question bank workflows. Core guidance focused on shifting priorities toward robust analytics modeling—specifically the Student At-Risk scoring framework—and ensuring AI content generation strictly adheres to pre-approved RAG sources rather than unconstrained on-the-fly generation.

---

**Key Discussions & Progress Demo**

* **Student Workspace:** Demonstrated lesson summary rendering from markdown files, quiz module execution, and quiz history logging.


* **Admin Dashboard & Pipeline Architecture:**
* Document ingestion pipeline automatically chunks uploaded PDFs into vector storage with version control.


* LangGraph guardrails implemented: prompt injection guards, question validators, off-topic summarization filters, and a 20,000-token context limit.


* Monorepo structured into backend, frontend, and Docker components with PostgreSQL.




* **Teacher Workspace & Question Bank:**
* Displayed class rosters (8A, 8B, 8C) with student-level attendance and mastery metrics.


* Question bank allows teachers to generate, approve, and export quiz questions to CSV.


* Suparna created the Student 360 database view tracking mastery and quiz completion metrics.




* **Sponsor Alignment:** Pranit shared feedback from sponsor Lakshmi emphasizing personalized student feedback post-quiz. Peeyush confirmed that granular question tagging will serve as the foundation for generating these tailored diagnostic insights.



---

**Mentor Feedback & Architectural Direction**

* **Prioritize Analytics & At-Risk Modeling:** With basic scaffolding functional, the team must focus heavily on the data science methodology behind the at-risk prediction model (e.g., metric selection, scoring logic, model performance, and justification).


* **Question Tagging & Benchmark Comparisons:** Granular tagging at the subtopic level (e.g., linear equations: single-variable vs. multivariable) should be used to diagnose persistent weak areas across chapters and compare individual performance against cohort benchmarks.


* **Controlled AI Generation (Human-in-the-Loop):** On-the-fly content generation must be strictly constrained to pre-approved, curriculum-aligned RAG sources with teacher oversight to eliminate hallucination risks. Simplified explanations (e.g., "explain like I'm 10") must reframe verified material rather than generate unmoderated external facts.


* **Pre-generated Quiz Pools:** Recommended generating pools of 50–60 multi-tiered questions (easy, medium, hard) per unit so students can re-attempt quizzes with progressive difficulty without generating unverified questions dynamically.
