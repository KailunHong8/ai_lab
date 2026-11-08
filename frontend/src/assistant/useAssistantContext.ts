import { useContext } from "react";
import { AssistantContext, type AssistantContextValue } from "./context";

export function useAssistantContext(): AssistantContextValue {
  const ctx = useContext(AssistantContext);
  if (!ctx) throw new Error("useAssistantContext must be used inside AssistantContextProvider");
  return ctx;
}
