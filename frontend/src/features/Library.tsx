import { Link } from "@tanstack/react-router";
import { useRef } from "react";
import { useDeleteDocument, useDocuments, useUpload } from "./documents";
import { ingestErrorMessage } from "./ingestError";

const STATUS_DOT: Record<string, string> = {
  ready: "bg-laurel",
  failed: "bg-danger",
};

export function Library() {
  const docs = useDocuments();
  const upload = useUpload();
  const remove = useDeleteDocument();
  const fileInput = useRef<HTMLInputElement>(null);
  const items = docs.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <section aria-labelledby="library-heading">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-lockup text-sm tracking-[0.14em] text-[#7A1F1F]">Your shelf</p>
          <h2 id="library-heading" className="theme-page-title mt-1">
            Library
          </h2>
        </div>
        <div>
          <input
            id="upload"
            ref={fileInput}
            type="file"
            accept=".epub,.pdf"
            disabled={upload.isPending}
            className="peer sr-only"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) upload.mutate(file, { onSettled: () => (e.target.value = "") });
            }}
          />
          <label
            htmlFor="upload"
            className={`btn-lockup btn-lockup-primary cursor-pointer ${
              upload.isPending ? "pointer-events-none opacity-60" : ""
            }`}
          >
            Upload a book (.epub or .pdf)
          </label>
        </div>
      </div>
      {upload.isPending && (
        <p role="status" className="notice mb-4">
          Uploading…
        </p>
      )}
      {upload.isError && (
        <p role="alert" className="alert mb-4">
          {upload.error.message}
        </p>
      )}

      {docs.isPending && <p role="status">Loading…</p>}
      {docs.isError && (
        <p role="alert" className="alert">
          Could not load your library.
        </p>
      )}
      {docs.isSuccess && items.length === 0 && (
        <div className="shelf-card p-10 text-center">
          <p className="text-lg leading-relaxed">Your library is empty. Upload a book you own to get started.</p>
          <p className="theme-muted mt-2 text-sm">
            Any DRM-free EPUB or PDF with selectable text is supported.
          </p>
        </div>
      )}

      <ul className="space-y-4">
        {items.map((d) => (
          <li key={d.id} className="shelf-card flex flex-wrap items-center justify-between gap-4 p-5">
            <div className="min-w-0">
              <p className="text-xl font-medium">
                <Link
                  to="/documents/$documentId"
                  params={{ documentId: d.id }}
                  className="theme-link font-medium no-underline hover:underline"
                >
                  {d.title}
                </Link>
              </p>
              <p className="theme-muted mt-1 flex items-center gap-2 text-sm">
                <span
                  aria-hidden="true"
                  className={`inline-block h-2.5 w-2.5 rounded-full ${STATUS_DOT[d.status] ?? "bg-gold"}`}
                />
                <span>
                  {d.format.toUpperCase()} · {(d.file_size / 1024 / 1024).toFixed(1)} MB ·{" "}
                  {d.status}
                </span>
              </p>
              {d.status === "failed" && (
                <p role="alert" className="alert mt-2 text-sm">
                  {ingestErrorMessage(d.error)}
                </p>
              )}
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <Link
                to="/documents/$documentId"
                params={{ documentId: d.id }}
                className="btn-lockup btn-lockup-outline btn-lockup-sm"
              >
                Open<span className="sr-only"> {d.title}</span>
              </Link>
              <button
                type="button"
                className="btn-lockup btn-lockup-sm border border-[#7A1F1F] bg-transparent text-[#7A1F1F]"
                onClick={() => {
                  if (window.confirm(`Delete "${d.title}"? This removes the file permanently.`))
                    remove.mutate(d.id);
                }}
              >
                Delete<span className="sr-only"> {d.title}</span>
              </button>
            </div>
          </li>
        ))}
      </ul>
      {docs.hasNextPage && (
        <button
          type="button"
          className="btn-lockup btn-lockup-outline btn-lockup-sm mt-6"
          onClick={() => docs.fetchNextPage()}
          disabled={docs.isFetchingNextPage}
        >
          Load more
        </button>
      )}
    </section>
  );
}
