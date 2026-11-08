import { NavLink } from "react-router-dom";

const links = [
  { to: "/portfolio", label: "Portfolio" },
  { to: "/research", label: "Research" },
  { to: "/strategies", label: "Strategies" },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Top bar */}
      <header className="bg-white border-b shadow-sm">
        <div className="max-w-6xl mx-auto px-4 py-3 flex flex-wrap items-center gap-x-6 gap-y-2">
          <span className="text-lg font-bold text-blue-700">Quant</span>
          <nav aria-label="Primary" className="flex flex-wrap gap-1">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                className={({ isActive }) =>
                  `px-2 sm:px-3 py-1.5 rounded text-sm font-medium ${
                    isActive ? "bg-blue-100 text-blue-700" : "text-gray-600 hover:text-gray-900 hover:bg-gray-100"
                  }`
                }
              >
                {l.label}
              </NavLink>
            ))}
          </nav>
          {/* Assistance, not a destination. Kept out of the primary nav on purpose. */}
          <NavLink
            to="/agent"
            className="ml-auto rounded border border-gray-200 px-3 py-1.5 text-sm text-gray-500 hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
          >
            Ask AI
          </NavLink>
        </div>
      </header>
      <main className="flex-1 max-w-6xl mx-auto w-full px-4 py-6">{children}</main>
    </div>
  );
}
