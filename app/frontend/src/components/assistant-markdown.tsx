"use client";

import ReactMarkdown from "react-markdown";

/** Render assistant prose with light markdown (bold/lists) — no raw ** markers. */
export function AssistantMarkdown({ content }: { content: string }) {
  return (
    <div className="text-sm leading-relaxed text-text">
      <ReactMarkdown
        components={{
          p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
          strong: ({ children }) => <strong className="font-semibold text-text">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          ul: ({ children }) => <ul className="mb-2 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
          ol: ({ children }) => <ol className="mb-2 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
          li: ({ children }) => <li>{children}</li>,
          h1: ({ children }) => <p className="mb-2 text-base font-semibold">{children}</p>,
          h2: ({ children }) => <p className="mb-2 text-base font-semibold">{children}</p>,
          h3: ({ children }) => <p className="mb-1.5 text-sm font-semibold">{children}</p>,
          table: () => null,
          thead: () => null,
          tbody: () => null,
          tr: () => null,
          th: () => null,
          td: () => null,
          hr: () => <hr className="my-3 border-border" />,
          a: ({ href, children }) => (
            <a href={href} className="text-accent-text underline-offset-2 hover:underline" target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
