import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "./AuthContext";
import { primaryRole, ROLE_STUDENT, roleHome } from "./roles";

/**
 * Student enrollment gate. Administrators and teachers are sent to their role
 * home instead of /enroll — enrollment applies to students only.
 */
export function RequireEnrollment({ children }: { children: React.ReactNode }) {
  const { user, enrolled, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="center-state" role="status">
        Loading…
      </div>
    );
  }

  const roles = user?.roles ?? [];
  const primary = primaryRole(roles);
  if (primary && primary !== ROLE_STUDENT) {
    return <Navigate to={roleHome(roles)} replace />;
  }

  if (!enrolled) {
    return <Navigate to="/enroll" replace state={{ from: location }} />;
  }

  return <>{children}</>;
}
