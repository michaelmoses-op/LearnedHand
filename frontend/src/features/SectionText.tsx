import { useState } from "react";

export type ChunkSpan = { ordinal: number; char_start: number; char_end: number };
export type Paragraph = { text: string; start: number; end: number };

/** Offsets can drift by a separator or two; be tolerant but never lenient about *unread* text. */
const SLACK = 2;

/** Paragraphs (blank-line separated) with their character offsets in `body`. */
export function paragraphSpans(title: string, body: string): Paragraph[] {
  const out: Paragraph[] = [];
  const push = (from: number, to: number) => {
    const raw = body.slice(from, to);
    const text = raw.trim();
    if (!text) return;
    const start = from + (raw.length - raw.trimStart().length);
    out.push({ text, start, end: start + text.length });
  };
  let last = 0;
  for (const m of body.matchAll(/\n{2,}/g)) {
    push(last, m.index);
    last = m.index + m[0].length;
  }
  push(last, body.length);
  // The section heading is shown separately; don't repeat it as the first paragraph.
  const first = out[0];
  if (first && first.text.toLowerCase() === title.trim().toLowerCase()) out.shift();
  return out;
}

export function paragraphsOf(title: string, body: string): string[] {
  return paragraphSpans(title, body).map((p) => p.text);
}

/**
 * Progress is stored per chunk (a few paragraphs). Marking a paragraph as "read up to here"
 * rounds DOWN to the last chunk that ends at or before that paragraph, so nothing unread is
 * ever counted as read. If the paragraph is inside the section's first chunk, that means the
 * chunk before it (the end of the previous section, or the very first passage).
 */
export function progressForParagraph(chunks: ChunkSpan[], paragraphEnd: number): number | null {
  const done = chunks.filter((c) => c.char_end <= paragraphEnd + SLACK);
  const best = done.at(-1);
  if (best) return best.ordinal;
  const first = chunks[0];
  return first ? Math.max(first.ordinal - 1, 0) : null;
}

/** Character offset in the section text up to which the reader has fully read (or -1). */
export function readUntil(chunks: ChunkSpan[], progress: number): number {
  return chunks.filter((c) => c.ordinal <= progress).reduce((m, c) => Math.max(m, c.char_end), -1);
}

export function SectionText({
  title,
  body,
  chunks,
  progress,
  showBookmark,
  disabled,
  onMark,
}: {
  title: string;
  body: string;
  chunks: ChunkSpan[];
  progress: number;
  showBookmark: boolean;
  disabled: boolean;
  onMark: (ordinal: number) => void;
}) {
  const paras = paragraphSpans(title, body);
  const [active, setActive] = useState<number | null>(null);
  const until = readUntil(chunks, progress);
  const isRead = (p: Paragraph) => until >= 0 && p.end <= until + SLACK;
  const lastRead = paras.reduce((m, p, i) => (isRead(p) ? i : m), -1);

  function mark(p: Paragraph) {
    const target = progressForParagraph(chunks, p.end);
    if (target !== null && !disabled) onMark(target);
    setActive(null);
  }

  return (
    <div className="book-text mt-3">
      {paras.map((p, i) => (
        <div key={p.start}>
          <p
            className={i === 0 ? "dropcap" : undefined}
            data-read={isRead(p) ? "true" : undefined}
            data-active={active === i ? "true" : undefined}
            tabIndex={0}
            title="Click for options, double-click to mark as read up to here"
            onClick={() => setActive(active === i ? null : i)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setActive(active === i ? null : i);
              }
            }}
            onDoubleClick={() => {
              window.getSelection()?.removeAllRanges(); // drop the word double-click selected
              mark(p);
            }}
          >
            {p.text}
          </p>
          {active === i && (
            <div className="book-toolbar" role="group" aria-label="Reading position">
              <button
                type="button"
                className="btn btn-sm"
                disabled={disabled}
                onClick={() => mark(p)}
              >
                I have read up to here
              </button>
              <span className="muted">
                Saves the end of the last full passage before this point, so nothing unread counts
                as read.
              </span>
            </div>
          )}
          {showBookmark && i === lastRead && i < paras.length - 1 && (
            <div className="bookmark-line" role="note">
              <span>You have read up to here</span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
