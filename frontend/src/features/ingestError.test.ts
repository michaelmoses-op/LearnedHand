import { expect, test } from "vitest";
import { ingestErrorMessage } from "./ingestError";

test("explains the common reasons a book cannot be read", () => {
  expect(ingestErrorMessage("PdfParseError: pdf_no_text_layer")).toMatch(/OCR/);
  expect(ingestErrorMessage("PdfParseError: pdf_encrypted")).toMatch(/password/);
  expect(
    ingestErrorMessage("EpubParseError: This EPUB is DRM-protected and cannot be read"),
  ).toMatch(/DRM-free/);
  expect(ingestErrorMessage("ValueError: ingest_failed")).toMatch(/Try uploading/);
  expect(ingestErrorMessage(null)).toBe("Processing failed.");
});
