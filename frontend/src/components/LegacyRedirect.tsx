import { Navigate, useLocation } from "react-router-dom";

// Forwards old URLs to their new home without dropping the query string or the
// router state that handoffs (e.g. Studio drafts, Simulation transfers) rely on.
export default function LegacyRedirect({ to }: { to: string }) {
  const location = useLocation();
  return <Navigate to={{ pathname: to, search: location.search }} state={location.state} replace />;
}
