import { Link } from "react-router";
export function UnauthorizedPage() {
  return (
    <main className="grid min-h-screen place-items-center bg-canvas p-5">
      <section className="card text-center">
        <p className="text-sm font-bold text-warning">403</p>
        <h1 className="text-3xl font-bold">Access denied</h1>
        <p className="my-4 text-slate-400">
          Your organization role does not allow this action.
        </p>
        <Link className="button" to="/dashboard">
          Return to dashboard
        </Link>
      </section>
    </main>
  );
}
export function NotFoundPage() {
  return (
    <main className="grid min-h-screen place-items-center bg-canvas p-5">
      <section className="card text-center">
        <p className="text-sm font-bold text-blue-400">404</p>
        <h1 className="text-3xl font-bold">Page not found</h1>
        <Link className="button mt-5" to="/dashboard">
          Return home
        </Link>
      </section>
    </main>
  );
}
