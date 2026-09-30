import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { BackToTop } from "./BackToTop";

afterEach(() => {
  Object.defineProperty(window, "scrollY", { value: 0, configurable: true });
});

test("appears only after scrolling down and scrolls to the top", async () => {
  const scrollTo = vi.fn();
  window.scrollTo = scrollTo as unknown as typeof window.scrollTo;
  render(<BackToTop />);
  expect(screen.queryByRole("button", { name: "Back to top" })).not.toBeInTheDocument();

  Object.defineProperty(window, "scrollY", { value: 900, configurable: true });
  act(() => {
    fireEvent.scroll(window);
  });
  await userEvent.click(await screen.findByRole("button", { name: "Back to top" }));
  expect(scrollTo).toHaveBeenCalledWith(expect.objectContaining({ top: 0 }));

  Object.defineProperty(window, "scrollY", { value: 0, configurable: true });
  act(() => {
    fireEvent.scroll(window);
  });
  expect(screen.queryByRole("button", { name: "Back to top" })).not.toBeInTheDocument();
});
