import { apiStream } from "./client";
import { ApiError } from "./types";
import type {
  GenerationRun,
  KnowledgeDocumentVersionStatus,
  MaterialVersionStatus,
} from "./types";

export type ProgressSubject =
  | { kind: "run"; id: string }
  | { kind: "version"; id: string };

export type ProgressSnapshot = GenerationRun | MaterialVersionStatus | KnowledgeDocumentVersionStatus;

export type StreamCloseReason = "terminal";

export function runSubject(id: string): ProgressSubject {
  return { kind: "run", id };
}

export function versionSubject(id: string): ProgressSubject {
  return { kind: "version", id };
}

function progressPath(subject: ProgressSubject): string {
  switch (subject.kind) {
    case "run":
      return `/progress/runs/${encodeURIComponent(subject.id)}`;
    case "version":
      return `/progress/versions/${encodeURIComponent(subject.id)}`;
    default: {
      const _never: never = subject;
      return _never;
    }
  }
}

type SseEvent = {
  event: string;
  data: string;
  id?: string;
};

async function* readSse(
  body: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<SseEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      if (signal?.aborted) {
        throw new DOMException("Aborted", "AbortError");
      }
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";
      for (const block of blocks) {
        const parsed = parseSseBlock(block);
        if (parsed !== null) {
          yield parsed;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseSseBlock(block: string): SseEvent | null {
  let event = "message";
  let id: string | undefined;
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith(":")) {
      continue;
    }
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
      continue;
    }
    if (line.startsWith("id:")) {
      id = line.slice(3).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (dataLines.length === 0) {
    return null;
  }
  return { event, data: dataLines.join("\n"), id };
}

export async function subscribeProgress(
  subject: ProgressSubject,
  options: {
    signal?: AbortSignal;
    lastEventId?: string;
    onSnapshot: (snapshot: ProgressSnapshot) => void;
  },
): Promise<void> {
  let lastEventId = options.lastEventId;
  while (!options.signal?.aborted) {
    const res = await apiStream(progressPath(subject), {
      signal: options.signal,
      lastEventId,
    });
    if (res.body === null) {
      throw new ApiError("Progress stream had no body", 502, null);
    }
    let closed = false;
    for await (const item of readSse(res.body, options.signal)) {
      switch (item.event) {
        case "snapshot": {
          options.onSnapshot(JSON.parse(item.data) as ProgressSnapshot);
          if (item.id) {
            lastEventId = item.id;
          }
          break;
        }
        case "close": {
          closed = true;
          return;
        }
        case "error": {
          const payload = JSON.parse(item.data) as { detail?: string; status?: number };
          throw new ApiError(payload.detail ?? "Progress stream failed", payload.status ?? 500, payload);
        }
        default:
          break;
      }
    }
    if (closed || options.signal?.aborted) {
      return;
    }
  }
  throw new DOMException("Aborted", "AbortError");
}

export async function watchProgress(
  subject: ProgressSubject,
  options: {
    signal?: AbortSignal;
    onSnapshot?: (snapshot: ProgressSnapshot) => void;
  } = {},
): Promise<ProgressSnapshot> {
  let last: ProgressSnapshot | undefined;
  await subscribeProgress(subject, {
    signal: options.signal,
    onSnapshot: (snapshot) => {
      last = snapshot;
      options.onSnapshot?.(snapshot);
    },
  });
  if (last === undefined) {
    throw new ApiError("Progress stream closed without a snapshot", 502, null);
  }
  return last;
}
