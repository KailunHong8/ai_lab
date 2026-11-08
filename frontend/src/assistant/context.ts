import { createContext } from "react";

export interface AssistantContextItem {
  id: string;
  label: string;
  value: string;
}

export interface AssistantContextValue {
  items: AssistantContextItem[];
  attach: (item: AssistantContextItem) => void;
  detach: (id: string) => void;
  clear: () => void;
  isOpen: boolean;
  open: () => void;
  close: () => void;
}

export const AssistantContext = createContext<AssistantContextValue | null>(null);
