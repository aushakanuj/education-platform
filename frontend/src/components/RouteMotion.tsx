import type { ReactNode } from "react";
import { useLocation } from "react-router-dom";

import { CrumbHost, HostedCrumbs } from "./Crumbs";

/** Page body fades independently of the hosted breadcrumb trail. */
export function RouteMotion({ children }: { children: ReactNode }) {
  const location = useLocation();

  return (
    <CrumbHost>
      <div className="route-motion">
        <div className="main__inner">
          <HostedCrumbs />
          {/* Keyed remount + CSS `animation-fill-mode: both` starts at opacity 0 on first paint. */}
          <div key={location.pathname} className="route-motion__page">
            {children}
          </div>
        </div>
      </div>
    </CrumbHost>
  );
}
