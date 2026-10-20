import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { BookText, paragraphsOf, reflowParagraphForReader } from "./BookText";

test("splits on blank lines and drops a repeated heading", () => {
  expect(
    paragraphsOf("Chapter One", "Chapter One\n\nFirst para.\n\n\nSecond para.\nsame para"),
  ).toEqual(["First para.", "Second para.\nsame para"]);
  expect(paragraphsOf("Other", "Kept heading\n\nText")).toEqual(["Kept heading", "Text"]);
});

test("reflowParagraphForReader joins EPUB hard line breaks", () => {
  expect(reflowParagraphForReader("Many\nshort\nlines")).toBe("Many short lines");
});

test("reader layout reflows hard line breaks into one wrap", () => {
  render(<BookText layout="reader" title="T" body={"Line alpha\nLine beta"} />);
  expect(screen.getByText("Line alpha Line beta")).toBeInTheDocument();
});

test("renders one <p> per paragraph", () => {
  render(<BookText title="T" body={"One.\n\nTwo.\n\nThree."} />);
  expect(document.querySelectorAll(".book-text p")).toHaveLength(3);
  expect(screen.getByText("Two.")).toBeInTheDocument();
});
