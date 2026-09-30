import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { paragraphsOf, SectionText } from "./SectionText";

test("splits on blank lines and drops a repeated heading", () => {
  expect(
    paragraphsOf("Chapter One", "Chapter One\n\nFirst para.\n\n\nSecond para.\nsame para"),
  ).toEqual(["First para.", "Second para.\nsame para"]);
  expect(paragraphsOf("Other", "Kept heading\n\nText")).toEqual(["Kept heading", "Text"]);
});

test("renders one <p> per paragraph", () => {
  render(<SectionText title="T" body={"One.\n\nTwo.\n\nThree."} />);
  expect(document.querySelectorAll(".book-text p")).toHaveLength(3);
  expect(screen.getByText("Two.")).toBeInTheDocument();
});
