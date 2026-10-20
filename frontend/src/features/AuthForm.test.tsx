import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { AuthForm } from "./AuthForm";

function setup(onSubmit = vi.fn().mockResolvedValue(undefined)) {
  render(
    <AuthForm
      submitLabel="Log in"
      onSubmit={onSubmit}
      pending={false}
      autoComplete="new-password"
    />,
  );
  return onSubmit;
}

test("validates email and password length before submitting", async () => {
  const onSubmit = setup();
  await userEvent.type(screen.getByLabelText("Email"), "not-an-email");
  await userEvent.type(screen.getByLabelText("Password"), "short");
  await userEvent.click(screen.getByRole("button", { name: /Log in|Enter/ }));
  expect(await screen.findByText("Enter a valid email")).toBeInTheDocument();
  expect(screen.getByText("At least 12 characters")).toBeInTheDocument();
  expect(onSubmit).not.toHaveBeenCalled();
});

test("submits valid credentials", async () => {
  const onSubmit = setup();
  await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
  await userEvent.type(screen.getByLabelText("Password"), "correct horse battery");
  await userEvent.click(screen.getByRole("button", { name: /Log in|Enter/ }));
  await waitFor(() => expect(onSubmit).toHaveBeenCalled());
  expect(onSubmit.mock.calls[0]?.[0]).toEqual({
    email: "a@example.com",
    password: "correct horse battery",
  });
});
