import { useCallback, useMemo, useState } from "react";
import { AssistantContext, type AssistantContextItem } from "./context";

// Workspaces attach what the user is looking at; the assistant panel shows the
// attachments as removable chips and sends them with the next message.
export default function AssistantContextProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<AssistantContextItem[]>([]);
  const [isOpen, setIsOpen] = useState(false);

  const attach = useCallback((item: AssistantContextItem) => {
    setItems((prev) => [...prev.filter((i) => i.id !== item.id), item]);
  }, []);

  const detach = useCallback((id: string) => {
    setItems((prev) => prev.filter((i) => i.id !== id));
  }, []);

  const clear = useCallback(() => setItems([]), []);
  const open = useCallback(() => setIsOpen(true), []);
  const close = useCallback(() => setIsOpen(false), []);

  const value = useMemo(
    () => ({ items, attach, detach, clear, isOpen, open, close }),
    [items, attach, detach, clear, isOpen, open, close],
  );

  return <AssistantContext.Provider value={value}>{children}</AssistantContext.Provider>;
}
