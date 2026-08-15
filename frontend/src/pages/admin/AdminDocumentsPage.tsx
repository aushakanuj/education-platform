import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import {
  listKnowledgeDocuments,
  pollKnowledgeDocumentVersionStatus,
  uploadKnowledgeDocument,
} from "../../api/adminIngest";
import { ApiError, type KnowledgeDocumentListItem } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Crumbs } from "../../components/Crumbs";
import { IngestStatusBadge } from "../../components/IngestStatusBadge";
import { PushButton } from "../../components/PushButton";

const DOC_TYPES = [
  { value: "policy", label: "Policy" },
  { value: "handbook", label: "Handbook" },
  { value: "other", label: "Other" },
];

const MOCK_SESSION_DOCS_ERROR =
  "Documents need a real administrator JWT. Sign in as admin@demo.school (not a fixture session).";

export function AdminDocumentsPage() {
  const { isDevMockSession } = useAuth();
  const [docs, setDocs] = useState<KnowledgeDocumentListItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [docType, setDocType] = useState("policy");
  const [requiredRoles, setRequiredRoles] = useState("administrator,teacher");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (isDevMockSession) {
      setDocs(null);
      setListError(MOCK_SESSION_DOCS_ERROR);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const items = await listKnowledgeDocuments();
      setDocs(items);
      setListError(null);
    } catch (err) {
      setDocs(null);
      setListError(
        err instanceof ApiError ? err.message : "Could not load knowledge documents.",
      );
    } finally {
      setLoading(false);
    }
  }, [isDevMockSession]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file || busy || isDevMockSession) return;

    const resolvedTitle = title.trim() || file.name.replace(/\.pdf$/i, "");
    const roles = requiredRoles
      .split(",")
      .map((r) => r.trim())
      .filter(Boolean);

    setBusy(true);
    setUploadError(null);
    setUploadStatus("processing");

    try {
      const accepted = await uploadKnowledgeDocument({
        file,
        title: resolvedTitle,
        docType,
        requiredRoles: roles,
      });
      setUploadStatus(accepted.lifecycle_status);
      const settled = await pollKnowledgeDocumentVersionStatus(accepted.version_id);
      setUploadStatus(settled.lifecycle_status);
      if (settled.failure_reason) {
        setUploadError(settled.failure_reason);
      }
      setFile(null);
      setTitle("");
      await refresh();
    } catch (err) {
      setUploadStatus(null);
      setUploadError(err instanceof ApiError ? err.message : "Upload failed. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="admin-documents">
      <Crumbs parts={[{ label: "Documents" }]} />
      <div className="back-row">
        <Link to="/admin/materials" className="btn btn--outline btn--sm">
          ← Back to materials
        </Link>
      </div>
      <header className="page-head">
        <p className="kicker">Administrator · knowledge ingest</p>
        <h1>Documents</h1>
        <p>
          Upload policy and handbook PDFs for async indexing. Processing status updates after
          upload; Policy chat retrieves from indexed documents via the live assistant API.
        </p>
      </header>

      <section className="panel admin-documents__upload" aria-labelledby="docs-upload-heading">
        <h2 id="docs-upload-heading" className="admin-documents__section-title">
          Upload document
        </h2>
        {isDevMockSession ? (
          <p className="form__error" role="alert">
            {MOCK_SESSION_DOCS_ERROR}
          </p>
        ) : (
          <form className="admin-upload" onSubmit={(e) => void onSubmit(e)}>
            <div className="form__field">
              <label className="form__label" htmlFor="knowledge-doc-title">
                Title
              </label>
              <input
                id="knowledge-doc-title"
                className="form__input"
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Attendance policy 2026"
                disabled={busy}
              />
            </div>
            <div className="admin-upload__row">
              <div className="form__field">
                <label className="form__label" htmlFor="knowledge-doc-type">
                  Document type
                </label>
                <select
                  id="knowledge-doc-type"
                  className="form__input"
                  value={docType}
                  onChange={(e) => setDocType(e.target.value)}
                  disabled={busy}
                >
                  {DOC_TYPES.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form__field">
                <label className="form__label" htmlFor="knowledge-doc-roles">
                  Required roles
                </label>
                <input
                  id="knowledge-doc-roles"
                  className="form__input"
                  type="text"
                  value={requiredRoles}
                  onChange={(e) => setRequiredRoles(e.target.value)}
                  placeholder="administrator,teacher"
                  disabled={busy}
                />
              </div>
            </div>
            <div className="form__field">
              <label className="form__label" htmlFor="knowledge-doc-file">
                PDF file
              </label>
              <input
                id="knowledge-doc-file"
                className="form__input"
                type="file"
                accept="application/pdf,.pdf"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                disabled={busy}
              />
            </div>
            {uploadError && (
              <p className="form__error" role="alert">
                {uploadError}
              </p>
            )}
            {uploadStatus && (
              <p className="admin-upload__status" role="status">
                Ingest: <IngestStatusBadge status={uploadStatus} />
              </p>
            )}
            <div className="admin-upload__actions">
              <PushButton type="submit" disabled={!file || busy} loading={busy}>
                {busy ? "Processing…" : "Upload PDF"}
              </PushButton>
            </div>
          </form>
        )}
      </section>

      <section className="panel" aria-labelledby="docs-list-heading">
        <h2 id="docs-list-heading" className="admin-documents__section-title">
          Indexed documents
        </h2>
        {loading && (
          <p className="muted" role="status">
            Loading documents…
          </p>
        )}
        {listError && !isDevMockSession && (
          <p className="form__error" role="alert">
            {listError}
          </p>
        )}
        {!loading && !listError && docs && docs.length === 0 && (
          <p className="muted" role="status">
            No knowledge documents yet. Upload a PDF to start ingest.
          </p>
        )}
        {!loading && !listError && docs && docs.length > 0 && (
          <ul className="list">
            {docs.map((doc, index) => {
              const latest = doc.latest_version;
              return (
                <li key={doc.id} className="list-item">
                  <span className="list-item__num">{index + 1}</span>
                  <div>
                    <p className="list-item__title">{doc.title}</p>
                    <p className="list-item__meta">
                      {doc.doc_type}
                      {latest
                        ? ` · v${latest.version_number}`
                        : " · no versions"}
                      {latest && latest.chunk_count > 0
                        ? ` · ${latest.chunk_count} chunks`
                        : ""}
                      {latest?.failure_reason ? ` · ${latest.failure_reason}` : ""}
                    </p>
                  </div>
                  {latest ? (
                    <IngestStatusBadge status={latest.lifecycle_status} />
                  ) : (
                    <span className="badge badge--locked">none</span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
