import { useEffect, useRef } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useAssistantContext } from "../assistant/useAssistantContext";
import AssistantChat from "./AssistantChat";

const links = [
  { to: "/portfolio", label: "Portfolio" },
  { to: "/research", label: "Research" },
  { to: "/strategies", label: "Strategies" },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const { isOpen, open, close } = useAssistantContext();
  const panelRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  // The legacy conversation route already shows the assistant full page.
  const onAssistantPage = location.pathname === "/agent";

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      close();
      triggerRef.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    panelRef.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [isOpen, close]);

  const closePanel = () => {
    close();
    triggerRef.current?.focus();
  };

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
          {!onAssistantPage && (
            <button
              ref={triggerRef}
              type="button"
              onClick={() => (isOpen ? closePanel() : open())}
              aria-expanded={isOpen}
              aria-controls="assistant-panel"
              className="ml-auto rounded border border-gray-200 px-3 py-1.5 text-sm text-gray-500 hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
            >
              Ask AI
            </button>
          )}
        </div>
      </header>
      <main className="flex-1 max-w-6xl mx-auto w-full px-4 py-6">{children}</main>

      {isOpen && (
        <aside
          id="assistant-panel"
          ref={panelRef}
          tabIndex={-1}
          role="dialog"
          aria-modal="false"
          aria-label="Ask AI"
          className="fixed right-0 top-0 z-40 flex h-dvh w-full max-w-md flex-col border-l bg-gray-50 p-4 shadow-2xl focus:outline-none"
        >
          <div className="flex justify-end">
            <button
              type="button"
              onClick={closePanel}
              aria-label="Close assistant"
              className="text-xl leading-none text-gray-400 hover:text-gray-600"
            >
              ×
            </button>
          </div>
          <div className="min-h-0 flex-1">
            <AssistantChat compact />
          </div>
        </aside>
      )}
    </div>
  );
}
