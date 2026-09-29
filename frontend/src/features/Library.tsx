import { useRef } from "react";
import { useDeleteDocument, useDocuments, useUpload } from "./documents";

export function Library() {
  const docs = useDocuments();
  const upload = useUpload();
  const remove = useDeleteDocument();
  const fileInput = useRef<HTMLInputElement>(null);
  const items = docs.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <section aria-labelledby="library-heading">
      <h2 id="library-heading" className="text-xl font-semibold">
        Library
      </h2>

      <div className="my-4">
        <label htmlFor="upload" className="block">
          Upload a book (.epub or .pdf)
        </label>
        <input
          id="upload"
          ref={fileInput}
          type="file"
          accept=".epub,.pdf"
          disabled={upload.isPending}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) upload.mutate(file, { onSettled: () => (e.target.value = "") });
          }}
        />
        {upload.isPending && <p role="status">Uploading…</p>}
        {upload.isError && (
          <p role="alert" className="text-red-700">
            {upload.error.message}
          </p>
        )}
      </div>

      {docs.isPending && <p role="status">Loading…</p>}
      {docs.isError && <p role="alert">Could not load your library.</p>}
      {docs.isSuccess && items.length === 0 && (
        <p>Your library is empty. Upload a book you own to get started.</p>
      )}

      <ul className="divide-y">
        {items.map((d) => (
          <li key={d.id} className="flex items-center justify-between py-2">
            <div>
              <p className="font-medium">{d.title}</p>
              <p className="text-sm text-neutral-600">
                {d.format.toUpperCase()} · {(d.file_size / 1024 / 1024).toFixed(1)} MB · {d.status}
              </p>
            </div>
            <button
              className="text-red-700 underline"
              onClick={() => {
                if (window.confirm(`Delete "${d.title}"? This removes the file permanently.`))
                  remove.mutate(d.id);
              }}
            >
              Delete<span className="sr-only"> {d.title}</span>
            </button>
          </li>
        ))}
      </ul>
      {docs.hasNextPage && (
        <button onClick={() => docs.fetchNextPage()} disabled={docs.isFetchingNextPage}>
          Load more
        </button>
      )}
    </section>
  );
}
