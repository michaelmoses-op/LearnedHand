/** Turn the stored ingest failure reason into something a reader can act on. */
const KNOWN: [RegExp, string][] = [
  [
    /pdf_no_text_layer/,
    "This PDF is a scan with no text layer, so there is nothing to read. Run it through OCR " +
      "(for example with OCRmyPDF) and upload the result.",
  ],
  [
    /pdf_encrypted/,
    "This PDF needs a password to open. Remove the password protection and upload it again.",
  ],
  [/pdf_too_many_pages/, "This PDF is longer than the 5,000-page limit. Try splitting it."],
  [/pdf_timeout|pdf_memory_limit/, "This PDF was too large or complex to process."],
  [/DRM/, "This EPUB is DRM-protected, so it cannot be read. Use a DRM-free copy."],
  [/no readable text sections/, "No readable text was found in this EPUB."],
  [/epub_invalid|EpubParseError|Corrupt ZIP|Invalid /, "This EPUB file is damaged or malformed."],
  [/pdf_invalid|PdfParseError/, "This PDF file is damaged or malformed."],
];

export function ingestErrorMessage(error: string | null | undefined): string {
  if (!error) return "Processing failed.";
  for (const [re, msg] of KNOWN) if (re.test(error)) return msg;
  return "Processing failed. Try uploading the file again.";
}
