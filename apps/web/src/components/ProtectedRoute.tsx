import { Navigate, Outlet, useLocation } from "react-router";
import { useAuth } from "../auth/AuthProvider";

export function ProtectedRoute() {
  const { me, loading } = useAuth();
  const location = useLocation();
  if (loading)
    return (
      <main className="grid min-h-screen place-items-center" aria-live="polite">
        Restoring session…
      </main>
    );
  return me ? (
    <Outlet />
  ) : (
    <Navigate
      to="/login"
      replace
      state={{ from: `${location.pathname}${location.search}${location.hash}` }}
    />
  );
}
