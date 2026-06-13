import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { api, type AiAskResponse } from "../api";

declare global {
  interface Window {
    puter?: {
      ai: { chat: (prompt: string) => Promise<unknown> };
    };
  }
}

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  source?: string;
}

function extractPuterText(resp: unknown): string {
  if (typeof resp === "string") return resp;
  if (resp && typeof resp === "object") {
    const obj = resp as Record<string, unknown>;
    if (typeof obj.message === "object" && obj.message) {
      const msg = obj.message as Record<string, unknown>;
      if (typeof msg.content === "string") return msg.content;
      if (Array.isArray(msg.content)) {
        return msg.content
          .map((c) => (typeof c === "object" && c && "text" in c ? String((c as { text: unknown }).text) : ""))
          .join("");
      }
    }
    if (typeof obj.text === "string") return obj.text;
  }
  return JSON.stringify(resp);
}

export default function AiAssistant() {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      text: "Hi, I'm the AI controller assistant for the NDLS↔CNB corridor. Ask me about current delays, predictions, or recommended actions.",
    },
  ]);
  const [loading, setLoading] = useState(false);

  async function send() {
    const q = question.trim();
    if (!q || loading) return;
    setMessages((m) => [...m, { role: "user", text: q }]);
    setQuestion("");
    setLoading(true);
    try {
      const { data } = await api.post<AiAskResponse>("/api/ai/ask", { question: q });
      if (data.source === "template" && window.puter?.ai?.chat) {
        // Backend has no Claude key - try client-side puter.js as a richer fallback.
        try {
          const resp = await window.puter.ai.chat(
            `You are the AI controller assistant for the NDLS<->CNB railway digital twin corridor. ` +
              `Answer concisely (under 120 words) for a train traffic controller. Question: ${q}`
          );
          setMessages((m) => [...m, { role: "assistant", text: extractPuterText(resp), source: "puter" }]);
          return;
        } catch {
          /* fall through to backend template answer */
        }
      }
      setMessages((m) => [...m, { role: "assistant", text: data.answer, source: data.source }]);
    } catch {
      setMessages((m) => [...m, { role: "assistant", text: "Sorry, the assistant is unavailable right now." }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <motion.button
        onClick={() => setOpen((o) => !o)}
        className="fixed bottom-20 md:bottom-6 right-6 z-50 h-14 w-14 rounded-full glass-strong glow-cyan flex items-center justify-center text-2xl"
        whileHover={{ scale: 1.08 }}
        whileTap={{ scale: 0.95 }}
      >
        🤖
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            className="fixed bottom-36 md:bottom-24 right-6 z-50 w-[90vw] max-w-sm glass-strong rounded-2xl p-4 flex flex-col gap-3"
            style={{ maxHeight: "70vh" }}
          >
            <div className="flex items-center justify-between">
              <div className="font-semibold text-slate-200">AI Controller Assistant</div>
              <button onClick={() => setOpen(false)} className="text-slate-400 hover:text-slate-200">
                ✕
              </button>
            </div>
            <div className="flex-1 overflow-y-auto flex flex-col gap-2 pr-1" style={{ maxHeight: "45vh" }}>
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={`text-sm rounded-xl px-3 py-2 ${
                    m.role === "user" ? "bg-cyan-400/10 self-end text-cyan-100" : "bg-white/5 text-slate-200"
                  }`}
                >
                  {m.text}
                  {m.source && <div className="text-[10px] text-slate-500 mt-1">source: {m.source}</div>}
                </div>
              ))}
              {loading && <div className="text-xs text-slate-400">Thinking...</div>}
            </div>
            <div className="flex gap-2">
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && send()}
                placeholder="Ask about delays, recommendations..."
                className="flex-1 glass rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-cyan-400/40"
              />
              <button
                onClick={send}
                disabled={loading}
                className="rounded-xl px-3 py-2 text-sm font-semibold bg-gradient-to-r from-cyan-500 to-violet-500 text-slate-900 disabled:opacity-50"
              >
                Ask
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
