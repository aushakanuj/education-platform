import { apiRequest } from "./client";
import type {
  IngestLifecycleStatus,
  KnowledgeDocumentAccepted,
  KnowledgeDocumentDetail,
  KnowledgeDocumentListItem,
  KnowledgeDocumentVersionStatus,
  MaterialIngestAccepted,
  MaterialVersionStatus,
} from "./types";

const TERMINAL_STATUSES = new Set<IngestLifecycleStatus>([
  "ready",
  "failed",
  "published",
  "superseded",
  "archived",
]);

export function isTerminalIngestStatus(status: IngestLifecycleStatus): boolean {
  return TERMINAL_STATUSES.has(status);
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = window.setTimeout(() => resolve(), ms);
    signal?.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

export async function uploadSubtopicMaterial(
  subtopicId: string,
  file: File,
  title: string,
): Promise<MaterialIngestAccepted> {
  const body = new FormData();
  body.append("file", file);
  body.append("title", title);
  return apiRequest<MaterialIngestAccepted>(
    `/admin/subtopics/${encodeURIComponent(subtopicId)}/materials`,
    { method: "POST", body },
  );
}

export async function getMaterialVersionStatus(
  versionId: string,
): Promise<MaterialVersionStatus> {
  return apiRequest<MaterialVersionStatus>(
    `/admin/material-versions/${encodeURIComponent(versionId)}`,
  );
}

export type PollOptions = {
  intervalMs?: number;
  signal?: AbortSignal;
};

export async function pollMaterialVersionStatus(
  versionId: string,
  options: PollOptions = {},
): Promise<MaterialVersionStatus> {
  const intervalMs = options.intervalMs ?? 1500;
  for (;;) {
    if (options.signal?.aborted) {
      throw new DOMException("Aborted", "AbortError");
    }
    const status = await getMaterialVersionStatus(versionId);
    if (isTerminalIngestStatus(status.lifecycle_status)) {
      return status;
    }
    await sleep(intervalMs, options.signal);
  }
}

export type KnowledgeDocumentUploadInput = {
  file: File;
  title: string;
  docType: string;
  requiredRoles?: string[];
};

export async function uploadKnowledgeDocument(
  input: KnowledgeDocumentUploadInput,
): Promise<KnowledgeDocumentAccepted> {
  const body = new FormData();
  body.append("file", input.file);
  body.append("title", input.title);
  body.append("doc_type", input.docType);
  if (input.requiredRoles && input.requiredRoles.length > 0) {
    body.append("required_roles", input.requiredRoles.join(","));
  }
  return apiRequest<KnowledgeDocumentAccepted>("/admin/knowledge-documents", {
    method: "POST",
    body,
  });
}

export async function listKnowledgeDocuments(): Promise<KnowledgeDocumentListItem[]> {
  const data = await apiRequest<
    KnowledgeDocumentListItem[] | { items: KnowledgeDocumentListItem[] }
  >("/admin/knowledge-documents");
  return Array.isArray(data) ? data : data.items;
}

export async function getKnowledgeDocument(
  documentId: string,
): Promise<KnowledgeDocumentDetail> {
  return apiRequest<KnowledgeDocumentDetail>(
    `/admin/knowledge-documents/${encodeURIComponent(documentId)}`,
  );
}

export async function getKnowledgeDocumentVersionStatus(
  versionId: string,
): Promise<KnowledgeDocumentVersionStatus> {
  return apiRequest<KnowledgeDocumentVersionStatus>(
    `/admin/knowledge-document-versions/${encodeURIComponent(versionId)}`,
  );
}

export async function pollKnowledgeDocumentVersionStatus(
  versionId: string,
  options: PollOptions = {},
): Promise<KnowledgeDocumentVersionStatus> {
  const intervalMs = options.intervalMs ?? 1500;
  for (;;) {
    if (options.signal?.aborted) {
      throw new DOMException("Aborted", "AbortError");
    }
    const status = await getKnowledgeDocumentVersionStatus(versionId);
    if (isTerminalIngestStatus(status.lifecycle_status)) {
      return status;
    }
    await sleep(intervalMs, options.signal);
  }
}
