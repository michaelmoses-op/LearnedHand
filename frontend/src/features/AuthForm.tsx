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

  const input =
    "mt-1 block w-full rounded border border-neutral-400 px-3 py-2 focus:outline-2 focus:outline-blue-600";

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">
      <div>
        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          autoComplete="email"
          aria-invalid={!!errors.email}
          className={input}
          {...register("email")}
        />
        {errors.email && (
          <p role="alert" className="text-sm text-red-700">
            {errors.email.message}
          </p>
        )}
      </div>
      <div>
        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          autoComplete={autoComplete}
          aria-invalid={!!errors.password}
          className={input}
          {...register("password")}
        />
        {errors.password && (
          <p role="alert" className="text-sm text-red-700">
            {errors.password.message}
          </p>
        )}
      </div>
      {serverError && (
        <p role="alert" className="text-sm text-red-700">
          {serverError}
        </p>
      )}
      <button
        type="submit"
        disabled={pending}
        className="rounded bg-blue-700 px-4 py-2 text-white disabled:opacity-60"
      >
        {submitLabel}
      </button>
    </form>
  );
}
