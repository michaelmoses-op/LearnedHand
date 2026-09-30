import { zodResolver } from "@hookform/resolvers/zod";
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
}

export function AuthForm({ submitLabel, onSubmit, serverError, pending, autoComplete }: Props) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<AuthFields>({ resolver: zodResolver(schema) });

  const input = "field";

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">
      <div>
        <label htmlFor="email" className="label">
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
        <label htmlFor="password" className="label">
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
      {serverError && (
        <p role="alert" className="alert mt-2 text-sm">
          {serverError}
        </p>
      )}
      <button type="submit" disabled={pending} className="btn w-full">
        {submitLabel}
      </button>
    </form>
  );
}
