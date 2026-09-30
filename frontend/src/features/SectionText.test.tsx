import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import {
  paragraphSpans,
  paragraphsOf,
  progressForParagraph,
  readUntil,
  SectionText,
} from "./SectionText";

test("splits on blank lines and drops a repeated heading", () => {
  expect(
    paragraphsOf("Chapter One", "Chapter One\n\nFirst para.\n\n\nSecond para.\nsame para"),
  ).toEqual(["First para.", "Second para.\nsame para"]);
  expect(paragraphsOf("Other", "Kept heading\n\nText")).toEqual(["Kept heading", "Text"]);
});

test("renders one <p> per paragraph", () => {
  render(
    <SectionText
      title="T"
      body={"One.\n\nTwo.\n\nThree."}
      chunks={[]}
      progress={0}
      showBookmark={false}
      disabled={false}
      onMark={() => undefined}
    />,
  );
  expect(document.querySelectorAll(".book-text p")).toHaveLength(3);
  expect(screen.getByText("Two.")).toBeInTheDocument();
});

test("paragraph offsets line up with the body text", () => {
  const body = "Alpha one.\n\nBeta two.\n\n\nGamma three.";
  const spans = paragraphSpans("x", body);
  expect(spans.map((p) => body.slice(p.start, p.end))).toEqual([
    "Alpha one.",
    "Beta two.",
    "Gamma three.",
  ]);
});

test("marking rounds down to the last chunk that ends at or before the paragraph", () => {
  const chunks = [
    { ordinal: 10, char_start: 0, char_end: 100 },
    { ordinal: 11, char_start: 102, char_end: 200 },
    { ordinal: 12, char_start: 202, char_end: 300 },
  ];
  expect(progressForParagraph(chunks, 100)).toBe(10); // ends exactly at chunk 10
  expect(progressForParagraph(chunks, 150)).toBe(10); // inside chunk 11: only 10 is fully read
  expect(progressForParagraph(chunks, 300)).toBe(12);
  expect(progressForParagraph(chunks, 40)).toBe(9); // inside the first chunk: the one before it
  expect(progressForParagraph([{ ordinal: 0, char_start: 0, char_end: 50 }], 10)).toBe(0);
  expect(progressForParagraph([], 10)).toBeNull();
  expect(readUntil(chunks, 11)).toBe(200);
  expect(readUntil(chunks, 9)).toBe(-1);
});
