import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "./AuthContext";
import { hasRole, roleHome, type AppRole } from "./roles";

/**
 * Gate a route tree to one or more roles.
 * Unauthenticated → /login; authenticated but wrong role → their role home.
 */
export function RequireRole({
  roles,
  children,
}: {
  roles: AppRole | AppRole[];
  children: React.ReactNode;
}) {
  const { user, loading } = useAuth();
  const location = useLocation();
  const allowed = Array.isArray(roles) ? roles : [roles];

  if (loading) {
    return (
      <div className="center-state" role="status">
        Loading…
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  const permitted = allowed.some((role) => hasRole(user.roles, role));
  if (!permitted) {
    return <Navigate to={roleHome(user.roles)} replace />;
  }

  return <>{children}</>;
}
