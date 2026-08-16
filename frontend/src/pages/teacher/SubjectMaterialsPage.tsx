import { useState } from "react";
import { Navigate, useParams } from "react-router-dom";

import { Crumbs } from "../../components/Crumbs";
import { getTeacherSubject } from "../../mocks/teacherAssignments";

type Tab = "lessons" | "quizzes";

export function SubjectMaterialsPage() {
  const { sectionId = "", subjectId = "" } = useParams();
  const match = getTeacherSubject(sectionId, subjectId);
  const [tab, setTab] = useState<Tab>("lessons");
  const [openTopicId, setOpenTopicId] = useState<string | null>(null);

  if (!match) {
    return <Navigate to="/teacher" replace />;
  }

  const { section, subject } = match;
  const activeTopicId = openTopicId ?? subject.topics[0]?.id ?? null;
  const activeTopic = subject.topics.find((t) => t.id === activeTopicId) ?? null;

  return (
    <>
      <Crumbs
        parts={[
          { label: "My classes", to: "/teacher" },
          { label: section.label, to: `/teacher/classes/${section.id}` },
          { label: subject.name },
        ]}
      />
      <header className="page-head">
        <p className="kicker">
          {section.label} · {subject.code}
        </p>
        <h1>{subject.name}</h1>
        <p>{subject.blurb} Read-only materials mock — no publish controls yet.</p>
      </header>

      <section
        className="teacher-progress-strip"
        aria-labelledby="teacher-progress-heading"
      >
        <div className="teacher-progress-strip__head">
          <h2 id="teacher-progress-heading">{subject.progress.label}</h2>
          <span className="teacher-progress-strip__pct">{subject.progress.pct}%</span>
        </div>
        <div
          className={`progress ${subject.progress.pct >= 100 ? "progress--complete" : "progress--in-progress"}`}
          aria-hidden="true"
        >
          <span style={{ width: `${subject.progress.pct}%` }} />
        </div>
        <p className="teacher-progress-strip__detail">{subject.progress.detail}</p>
      </section>

      <div className="teacher-materials">
        <aside className="teacher-materials__topics" aria-label="Units">
          <h2 className="section-title">Units</h2>
          <ul className="teacher-topic-list">
            {subject.topics.map((topic) => {
              const isActive = topic.id === activeTopicId;
              return (
                <li key={topic.id}>
                  <button
                    type="button"
                    className={`teacher-topic-list__btn${isActive ? " is-active" : ""}`}
                    aria-current={isActive ? "true" : undefined}
                    onClick={() => setOpenTopicId(topic.id)}
                  >
                    <span>{topic.title}</span>
                    <span className="teacher-topic-list__meta">
                      {topic.lessons.length} lessons · {topic.quizzes.length} quizzes
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </aside>

        <div className="teacher-materials__detail">
          {activeTopic ? (
            <>
              <div className="teacher-materials__tabs" role="tablist" aria-label="Material type">
                <button
                  type="button"
                  role="tab"
                  aria-selected={tab === "lessons"}
                  className={`teacher-tab${tab === "lessons" ? " is-active" : ""}`}
                  onClick={() => setTab("lessons")}
                >
                  Lessons
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={tab === "quizzes"}
                  className={`teacher-tab${tab === "quizzes" ? " is-active" : ""}`}
                  onClick={() => setTab("quizzes")}
                >
                  Quizzes
                </button>
              </div>

              <h3 className="teacher-materials__topic-title">{activeTopic.title}</h3>

              {tab === "lessons" ? (
                <ul className="teacher-item-list">
                  {activeTopic.lessons.map((lesson) => (
                    <li key={lesson.id} className="teacher-item-list__row">
                      <span>{lesson.title}</span>
                      <span
                        className={`badge ${lesson.status === "published" ? "badge--ok" : "badge--warn"}`}
                      >
                        {lesson.status === "published" ? "Published" : "Draft"}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <ul className="teacher-item-list">
                  {activeTopic.quizzes.map((quiz) => (
                    <li key={quiz.id} className="teacher-item-list__row">
                      <span>
                        {quiz.title}
                        <span className="teacher-item-list__kind">
                          {quiz.kind === "topic" ? "Topic mastery" : "Subtopic"}
                        </span>
                      </span>
                      <span
                        className={`badge ${quiz.status === "published" ? "badge--ok" : "badge--warn"}`}
                      >
                        {quiz.status === "published" ? "Published" : "Draft"}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <div className="alert alert--info">No units published for this subject yet.</div>
          )}
        </div>
      </div>
    </>
  );
}
