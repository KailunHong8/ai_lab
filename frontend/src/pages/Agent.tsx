import { useRef, useState } from "react";
import { agentChat, clearSession } from "../api/client";

interface Message {
  role: "user" | "assistant";
  text: string;
}

const SESSION_ID = "default";

export default function Agent() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;
    const userMsg = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: userMsg }]);
    setLoading(true);
    try {
      const data = await agentChat(userMsg, SESSION_ID);
      setMessages((prev) => [...prev, { role: "assistant", text: data.reply }]);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: `Error: ${err.response?.data?.detail ?? err.message}` },
      ]);
    } finally {
      setLoading(false);
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    }
  };

  const handleClear = async () => {
    await clearSession(SESSION_ID);
    setMessages([]);
  };

  return (
    <div className="flex flex-col h-[calc(100vh-96px)]">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">AI Trading Copilot</h1>
        <button
          onClick={handleClear}
          className="text-xs text-gray-500 hover:text-red-500 border rounded px-2 py-1"
        >
          Clear chat
        </button>
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto bg-white rounded-xl shadow p-4 flex flex-col gap-3">
        {messages.length === 0 && (
          <p className="text-gray-400 text-sm text-center mt-8">
            Ask anything about your portfolio, trading strategies, or financial concepts.
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[80%] rounded-xl px-4 py-2 text-sm whitespace-pre-wrap ${
                m.role === "user"
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-900"
              }`}
            >
              {m.text}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-xl px-4 py-2 text-sm text-gray-500 animate-pulse">
              Thinking…
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form onSubmit={send} className="mt-3 flex gap-2">
        <input
          className="flex-1 border rounded-xl px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="e.g. What's a good CAPM-based strategy for my portfolio?"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="bg-blue-600 text-white rounded-xl px-5 py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}
