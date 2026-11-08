import { NavLink } from "react-router-dom";

// Local view tabs for a workspace. These are parts of one job, not navigation.
export default function WorkspaceTabs({
  tabs,
}: {
  tabs: { to: string; label: string; end?: boolean }[];
}) {
  return (
    <nav aria-label="Workspace views" className="mb-6 flex flex-wrap gap-1 border-b">
      {tabs.map((t) => (
        <NavLink
          key={t.to}
          to={t.to}
          end={t.end}
          className={({ isActive }) =>
            `-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
              isActive
                ? "border-blue-600 text-blue-700"
                : "border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-800"
            }`
          }
        >
          {t.label}
        </NavLink>
      ))}
    </nav>
  );
}
