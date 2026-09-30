import { Link } from "@tanstack/react-router";
import { useRef } from "react";
import { useDeleteDocument, useDocuments, useUpload } from "./documents";

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
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow">Your shelf</p>
          <h2 id="library-heading" className="text-3xl font-semibold">
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
            className={`btn cursor-pointer peer-focus-visible:outline-3 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-gold ${
              upload.isPending ? "opacity-60" : ""
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
        <div className="panel p-10 text-center">
          <p className="text-lg">Your library is empty. Upload a book you own to get started.</p>
          <p className="muted mt-2 text-sm">EPUB and text-based PDF files are supported.</p>
        </div>
      )}

      <ul className="space-y-4">
        {items.map((d) => (
          <li
            key={d.id}
            className="panel flex flex-wrap items-center justify-between gap-4 border-l-8 border-l-burgundy p-5"
          >
            <div className="min-w-0">
              <p className="text-xl font-semibold">
                <Link to="/documents/$documentId" params={{ documentId: d.id }}>
                  {d.title}
                </Link>
              </p>
              <p className="muted mt-1 flex items-center gap-2 text-sm">
                <span
                  aria-hidden="true"
                  className={`inline-block h-2.5 w-2.5 rounded-full ${STATUS_DOT[d.status] ?? "bg-gold"}`}
                />
                <span>
                  {d.format.toUpperCase()} · {(d.file_size / 1024 / 1024).toFixed(1)} MB ·{" "}
                  {d.status}
                </span>
              </p>
            </div>
            <div className="flex shrink-0 gap-2">
              <Link
                to="/documents/$documentId"
                params={{ documentId: d.id }}
                className="btn btn-sm"
              >
                Open<span className="sr-only"> {d.title}</span>
              </Link>
              <button
                className="btn btn-danger btn-sm"
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
          className="btn btn-secondary mt-4"
          onClick={() => docs.fetchNextPage()}
          disabled={docs.isFetchingNextPage}
        >
          Load more
        </button>
      )}
    </section>
  );
}
