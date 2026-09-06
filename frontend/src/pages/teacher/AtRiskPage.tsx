import { useMemo, useState } from "react";

import { dismissAtRiskFlag, type AtRiskFlag } from "../../api/atRisk";
import { AtRiskDismissDialog } from "../../components/AtRiskDismissDialog";
import { AtRiskFilterBar } from "../../components/AtRiskFilterBar";
import { AtRiskFlagsTable } from "../../components/AtRiskFlagsTable";
import { Crumbs } from "../../components/Crumbs";
import { filterAtRiskFlags, type AtRiskTierFilter } from "../../lib/atRiskFilters";
import { useAtRiskFlags } from "../../lib/useAtRiskFlags";

export function AtRiskPage() {
  const { loading, error, flags, removeFlag } = useAtRiskFlags();
  const [tier, setTier] = useState<AtRiskTierFilter>("all");
  const [query, setQuery] = useState("");
  const [target, setTarget] = useState<AtRiskFlag | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [dismissError, setDismissError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const visible = useMemo(() => filterAtRiskFlags(flags, tier, query), [flags, tier, query]);

  async function confirmDismiss(dismissalNote: string) {
    if (!target) return;
    setBusyId(target.id);
    setDismissError(null);
    try {
      await dismissAtRiskFlag(target.id, dismissalNote);
      removeFlag(target.id);
      setNote(`Dismissed ${target.student_name}'s flag.`);
      setTarget(null);
    } catch (err: unknown) {
      setDismissError(err instanceof Error ? err.message : "Could not dismiss that flag.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <Crumbs parts={[{ label: "My classes", to: "/teacher" }, { label: "At-risk flags" }]} />
      <header className="page-head">
        <p className="kicker">Teacher · early warning</p>
        <h1>
          {flags.length} flag{flags.length === 1 ? "" : "s"}
        </h1>
        <p>Students in your classes the engine flagged, and exactly why.</p>
      </header>

      {loading && <div className="banner banner--info">Loading at-risk flags…</div>}

      {error && (
        <div className="banner banner--warning" role="alert">
          {error}
        </div>
      )}

      {dismissError && (
        <div className="banner banner--warning" role="alert">
          {dismissError}
        </div>
      )}

      {note && !dismissError && (
        <div className="banner banner--info" role="status">
          {note}
        </div>
      )}

      {!loading && !error && flags.length === 0 && (
        <div className="banner banner--info" role="status">
          Nobody in your classes is flagged right now.
        </div>
      )}

      {!loading && !error && flags.length > 0 && (
        <>
          <AtRiskFilterBar
            flags={flags}
            tier={tier}
            query={query}
            onTierChange={setTier}
            onQueryChange={setQuery}
          />
          {visible.length === 0 ? (
            <div className="banner banner--info" role="status">
              No flag matches “{query}”.
            </div>
          ) : (
            <AtRiskFlagsTable flags={visible} busyId={busyId} onDismiss={setTarget} />
          )}
        </>
      )}

      <AtRiskDismissDialog
        flag={target}
        busy={busyId !== null}
        onCancel={() => setTarget(null)}
        onConfirm={(dismissalNote) => void confirmDismiss(dismissalNote)}
      />
    </>
  );
}
