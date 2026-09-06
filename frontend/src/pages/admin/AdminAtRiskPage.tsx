import { useMemo, useState } from "react";

import { dismissAtRiskFlag, recomputeAtRisk, type AtRiskFlag } from "../../api/atRisk";
import { AtRiskDismissDialog } from "../../components/AtRiskDismissDialog";
import { AtRiskFilterBar } from "../../components/AtRiskFilterBar";
import { AtRiskFlagsTable } from "../../components/AtRiskFlagsTable";
import { Crumbs } from "../../components/Crumbs";
import { PushButton } from "../../components/PushButton";
import { filterAtRiskFlags, type AtRiskTierFilter } from "../../lib/atRiskFilters";
import { useAtRiskFlags } from "../../lib/useAtRiskFlags";

export function AdminAtRiskPage() {
  const { loading, error, flags, removeFlag, refresh } = useAtRiskFlags();
  const [tier, setTier] = useState<AtRiskTierFilter>("all");
  const [query, setQuery] = useState("");
  const [target, setTarget] = useState<AtRiskFlag | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [recomputing, setRecomputing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const visible = useMemo(() => filterAtRiskFlags(flags, tier, query), [flags, tier, query]);

  async function onRecompute() {
    if (recomputing) return;
    setRecomputing(true);
    setActionError(null);
    try {
      const result = await recomputeAtRisk();
      setNote(
        `Checked ${result.students_considered} students: ${result.flags_active} active flags` +
          (result.flags_resolved > 0 ? `, ${result.flags_resolved} resolved.` : "."),
      );
      await refresh();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Recompute failed.");
    } finally {
      setRecomputing(false);
    }
  }

  async function confirmDismiss(dismissalNote: string) {
    if (!target) return;
    setBusyId(target.id);
    setActionError(null);
    try {
      await dismissAtRiskFlag(target.id, dismissalNote);
      removeFlag(target.id);
      setNote(`Dismissed ${target.student_name}'s flag.`);
      setTarget(null);
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Could not dismiss that flag.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <Crumbs parts={[{ label: "At-risk flags" }]} />
      <header className="page-head page-head--with-actions">
        <div>
          <p className="kicker">Administrator · school-wide</p>
          <h1>
            {flags.length} active flag{flags.length === 1 ? "" : "s"}
          </h1>
          <p>Every active flag across the school, including attendance concerns no single teacher owns.</p>
        </div>
        <div className="page-head__actions">
          <PushButton onClick={() => void onRecompute()} disabled={recomputing} loading={recomputing}>
            {recomputing ? "Recomputing…" : "Recompute now"}
          </PushButton>
        </div>
      </header>

      {loading && <div className="banner banner--info">Loading at-risk flags…</div>}

      {error && (
        <div className="banner banner--warning" role="alert">
          {error}
        </div>
      )}

      {actionError && (
        <div className="banner banner--warning" role="alert">
          {actionError}
        </div>
      )}

      {note && !actionError && (
        <div className="banner banner--info" role="status">
          {note}
        </div>
      )}

      {!loading && !error && flags.length === 0 && (
        <div className="banner banner--info" role="status">
          No active flags. Try "Recompute now" if the school's data has changed since the last
          run.
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
