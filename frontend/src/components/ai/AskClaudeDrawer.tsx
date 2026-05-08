import { useEffect, useRef, useState } from "react";
import { Heading, TextArea, Button, Badge } from "@radix-ui/themes";
import { X, PaperPlaneTilt } from "@phosphor-icons/react";
import { useLocation } from "react-router-dom";
import { streamChat } from "../../api/aiClient";
import { usePageContext } from "./usePageContext";
import MessageBubble from "./MessageBubble";
import SuggestedPrompts from "./SuggestedPrompts";
import type { AIMessage, AIToolPart } from "../../types";

interface AskClaudeDrawerProps {
  open: boolean;
  onClose: () => void;
}

function newAssistant(): AIMessage {
  return { role: "assistant", parts: [], inFlight: true };
}

export default function AskClaudeDrawer({ open, onClose }: AskClaudeDrawerProps) {
  const pageContext = usePageContext();
  const { pathname } = useLocation();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<AIMessage[]>([]);
  const [pending, setPending] = useState(false);
  const scrollerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new content.
  useEffect(() => {
    if (!scrollerRef.current) return;
    scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
  }, [messages]);

  // Focus the input when the drawer opens.
  const inputRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || pending) return;
    setInput("");
    setPending(true);

    const userMsg: AIMessage = {
      role: "user",
      parts: [{ kind: "text", text: trimmed }],
    };
    const assistant = newAssistant();
    const history = [...messages, userMsg, assistant];
    setMessages(history);

    const toolIndex = new Map<string, AIToolPart>();

    function patchAssistant(mutator: (m: AIMessage) => AIMessage) {
      setMessages((prev) => {
        const next = prev.slice();
        next[next.length - 1] = mutator(next[next.length - 1]);
        return next;
      });
    }

    try {
      await streamChat(
        [...messages, userMsg],
        pageContext,
        pathname,
        {
          onTextDelta: (delta) => {
            patchAssistant((m) => {
              const parts = m.parts.slice();
              const last = parts[parts.length - 1];
              if (last && last.kind === "text") {
                parts[parts.length - 1] = { kind: "text", text: last.text + delta };
              } else {
                parts.push({ kind: "text", text: delta });
              }
              return { ...m, parts };
            });
          },
          onToolUseStart: ({ id, name, input }) => {
            const tp: AIToolPart = {
              kind: "tool",
              id, name: name as AIToolPart["name"],
              input,
            };
            toolIndex.set(id, tp);
            patchAssistant((m) => ({ ...m, parts: [...m.parts, tp] }));
          },
          onToolUseEnd: ({ id, ok, error, row_count, truncated, elapsed_ms }) => {
            const tp = toolIndex.get(id);
            if (!tp) return;
            tp.ok = ok;
            tp.error = error;
            tp.rowCount = row_count;
            tp.truncated = truncated;
            tp.elapsedMs = elapsed_ms;
            // Force a re-render
            patchAssistant((m) => ({
              ...m,
              parts: m.parts.map((p) =>
                p.kind === "tool" && p.id === id ? { ...tp } : p
              ),
            }));
          },
          onDone: () => {
            patchAssistant((m) => ({ ...m, inFlight: false }));
          },
          onError: (msg) => {
            patchAssistant((m) => ({
              ...m,
              parts: [...m.parts, { kind: "text", text: `\n\n_Error: ${msg}_` }],
              inFlight: false,
            }));
          },
        },
      );
    } catch (err) {
      patchAssistant((m) => ({
        ...m,
        parts: [...m.parts, { kind: "text", text: `\n\n_Network error: ${String(err)}_` }],
        inFlight: false,
      }));
    } finally {
      setPending(false);
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      send(input);
    }
  }

  if (!open) return null;
  const empty = messages.length === 0;

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div
        className="relative ml-auto h-full flex flex-col"
        style={{
          width: 420,
          background: "var(--color-background)",
          borderLeft: "1px solid var(--gray-6)",
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--gray-6)]">
          <div className="flex items-center gap-2">
            <Heading size="3">Ask Claude</Heading>
            {pageContext && (
              <Badge size="1" variant="soft" color="jade">
                Looking at {pageContext.id}
              </Badge>
            )}
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-[var(--gray-3)]">
            <X size={18} />
          </button>
        </div>

        {/* Messages */}
        <div ref={scrollerRef} className="flex-1 overflow-y-auto px-4 py-3">
          {empty ? (
            <SuggestedPrompts context={pageContext} onPick={(p) => setInput(p)} />
          ) : (
            messages.map((m, i) => <MessageBubble key={i} message={m} />)
          )}
        </div>

        {/* Input */}
        <div className="border-t border-[var(--gray-6)] p-3">
          <TextArea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask anything about your data… (⌘+Enter to send)"
            rows={3}
            disabled={pending}
          />
          <div className="flex justify-end mt-2">
            <Button
              onClick={() => send(input)}
              disabled={pending || !input.trim()}
              size="2"
            >
              <PaperPlaneTilt size={14} /> Send
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
