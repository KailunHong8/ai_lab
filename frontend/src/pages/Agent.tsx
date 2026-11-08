import AssistantChat from "../components/AssistantChat";

// Compatibility route: the same conversation component used by the contextual panel,
// kept so existing /agent links and session history continue to work.
export default function Agent() {
  return <AssistantChat />;
}
