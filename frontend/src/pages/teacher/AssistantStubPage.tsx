import { Crumbs } from "../../components/Crumbs";

/**
 * Navigation stub. Ask-the-data is being built separately (text-to-SQL), and this page is
 * where it lands; the route is kept so the sidebar entry does not become a dead link.
 */
export function AssistantStubPage() {
  return (
    <>
      <Crumbs parts={[{ label: "My classes", to: "/teacher" }, { label: "Assistant" }]} />
      <header className="page-head">
        <p className="kicker">Teacher · coming later</p>
        <h1>Assistant</h1>
        <p>
          Asking questions about your classes in plain English is being built as part of the
          ask-the-data work. It will appear here.
        </p>
      </header>
      <div className="banner banner--info" role="status">
        Not wired up yet. Your class data is live everywhere else in this workspace.
      </div>
    </>
  );
}
