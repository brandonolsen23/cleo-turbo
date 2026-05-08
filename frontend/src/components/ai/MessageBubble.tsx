import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Link as RouterLink } from "react-router-dom";
import { Text } from "@radix-ui/themes";
import type { AIMessage, AIToolPart } from "../../types";
import ToolCallBlock from "./ToolCallBlock";

export default function MessageBubble({ message }: { message: AIMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3`}>
      <div
        className={`max-w-[88%] rounded-lg px-3 py-2 text-[14px] leading-relaxed ${
          isUser ? "bg-[var(--accent-3)]" : "bg-[var(--gray-2)]"
        }`}
      >
        {message.parts.map((part, i) => {
          if (part.kind === "tool") {
            return <ToolCallBlock key={i} part={part as AIToolPart} />;
          }
          return (
            <ReactMarkdown
              key={i}
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ href = "", children, ...rest }) => {
                  if (href.startsWith("/")) {
                    return (
                      <RouterLink
                        to={href}
                        style={{ color: "var(--accent-11)" }}
                        className="no-underline hover:underline"
                      >
                        {children}
                      </RouterLink>
                    );
                  }
                  return (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: "var(--accent-11)" }}
                      className="no-underline hover:underline"
                      {...rest}
                    >
                      {children}
                    </a>
                  );
                },
                code: ({ children }) => (
                  <code className="px-1 py-0.5 rounded bg-[var(--gray-3)] text-[12px]">{children}</code>
                ),
                pre: ({ children }) => (
                  <pre className="p-2 rounded bg-[var(--gray-3)] overflow-x-auto text-[12px]">{children}</pre>
                ),
                table: ({ children }) => (
                  <table className="my-2 text-[12px] border-collapse w-full">{children}</table>
                ),
                th: ({ children }) => (
                  <th className="px-2 py-1 text-left bg-[var(--gray-3)] border border-[var(--gray-5)]">{children}</th>
                ),
                td: ({ children }) => (
                  <td className="px-2 py-1 border border-[var(--gray-5)]">{children}</td>
                ),
              }}
            >
              {part.text}
            </ReactMarkdown>
          );
        })}
        {message.inFlight && (
          <Text size="1" style={{ color: "var(--gray-9)" }}>▍</Text>
        )}
      </div>
    </div>
  );
}
