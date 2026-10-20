import { zodResolver } from "@hookform/resolvers/zod";
import type { ReactNode } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

const schema = z.object({
  email: z.string().email("Enter a valid email").max(254),
  password: z.string().min(12, "At least 12 characters").max(128),
});
export type AuthFields = z.infer<typeof schema>;

interface Props {
  submitLabel: string;
  onSubmit: (values: AuthFields) => Promise<void>;
  serverError?: string | undefined;
  pending: boolean;
  autoComplete: "current-password" | "new-password";
  variant?: "default" | "lockup";
  afterPassword?: ReactNode;
  footer?: ReactNode;
}

export function AuthForm({
  submitLabel,
  onSubmit,
  serverError,
  pending,
  autoComplete,
  variant = "default",
  afterPassword,
  footer,
}: Props) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<AuthFields>({ resolver: zodResolver(schema) });

  const lockup = variant === "lockup";
  const input = lockup ? "auth-field" : "field";
  const labelClass = lockup ? "auth-label" : "label";

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className={lockup ? "" : "space-y-4"}>
      <div>
        <label htmlFor="email" className={labelClass}>
          Email
        </label>
        <input
          id="email"
          type="email"
          autoComplete="email"
          aria-invalid={!!errors.email}
          className={input}
          {...register("email")}
        />
        {errors.email && (
          <p role="alert" className="alert mt-2 text-sm">
            {errors.email.message}
          </p>
        )}
      </div>
      <div>
        <label htmlFor="password" className={labelClass}>
          Password
        </label>
        <input
          id="password"
          type="password"
          autoComplete={autoComplete}
          aria-invalid={!!errors.password}
          className={input}
          {...register("password")}
        />
        {errors.password && (
          <p role="alert" className="alert mt-2 text-sm">
            {errors.password.message}
          </p>
        )}
      </div>
      {afterPassword}
      {serverError && (
        <p role="alert" className="alert mt-2 text-sm">
          {serverError}
        </p>
      )}
      <button
        type="submit"
        disabled={pending}
        className={lockup ? "btn-lockup btn-lockup-primary mt-1 w-full" : "btn w-full"}
      >
        {submitLabel}
      </button>
      {footer}
    </form>
  );
}
