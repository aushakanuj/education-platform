import type { IngestLifecycleStatus } from "../api/types";

const BADGE_CLASS: Record<string, string> = {
  ready: "badge badge--ok",
  published: "badge badge--ok",
  processing: "badge badge--info",
  draft: "badge badge--info",
  failed: "badge badge--warn",
  superseded: "badge badge--locked",
  archived: "badge badge--locked",
};

export function IngestStatusBadge({ status }: { status: IngestLifecycleStatus | string }) {
  const className = BADGE_CLASS[status] ?? "badge";
  return <span className={className}>{status}</span>;
}
