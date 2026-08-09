import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "./AuthContext";

export function RequireEnrollment({ children }: { children: React.ReactNode }) {
  const { enrolled, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="center-state" role="status">
        Loading…
      </div>
    );
  }

  if (!enrolled) {
    return <Navigate to="/enroll" replace state={{ from: location }} />;
  }

  return <>{children}</>;
}
