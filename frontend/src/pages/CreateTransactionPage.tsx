import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useCreateTransaction } from "../hooks/useCreateTransaction";
import { ScoreResultCard } from "./ScoreResultCard";
import { PageTransition } from "../components/PageTransition";
import { Sidebar } from "../components/Sidebar";
import { Button } from "../components/Button";
import { Field } from "../components/Field";
import { Input } from "../components/Input";
import type { ScoreResponse } from "../api/transactions";

const transactionSchema = z.object({
  amount: z.coerce.number().positive("El monto debe ser mayor a 0"),
  currency: z.string().length(3, "La moneda debe tener 3 caracteres"),
  merchant_name: z.string().min(1, "El nombre del comercio es requerido"),
  merchant_category: z.string().optional(),
  card_last4: z
    .string()
    .length(4, "Debe tener 4 dígitos")
    .regex(/^\d{4}$/, "Solo dígitos"),
  // A30: user_id used to be a hidden required field fed from the auth store.
  // It was a permanent dead end: authStore sets isAuthenticated unconditionally
  // and leaves `user` null when the token fails to decode, and ProtectedRoute
  // gates on isAuthenticated only, so `{isAuthenticated: true, user: null}` was
  // reachable — and an empty user_id fails validation forever, leaving the
  // submit button permanently disabled with no error rendered, because the
  // hidden input was the one field with no error node.
  //
  // It was also dead weight: the server ignores payload.user_id and always uses
  // the authenticated identity (F2), and the schema marks it deprecated. So a
  // hidden, un-diagnosable, permanently-blocking field was gating a submit for
  // a value the server discards.
});

type TransactionFormData = z.infer<typeof transactionSchema>;

export default function CreateTransactionPage() {
  const [result, setResult] = useState<ScoreResponse | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isValid },
  } = useForm<TransactionFormData>({
    resolver: zodResolver(transactionSchema),
    mode: "onChange",
    defaultValues: {
      merchant_category: "",
    },
  });

  const mutation = useCreateTransaction();

  const onSubmit = async (data: TransactionFormData) => {
    try {
      const response = await mutation.mutateAsync(data);
      setResult(response);
    } catch {
      // Error handled by useCreateTransaction onError → toast
    }
  };

  return (
    <div className="min-h-screen bg-page-bg flex overflow-x-hidden">
      <Sidebar activeItem="transactions" />
      <div className="flex-1 p-6 overflow-y-auto" style={{ maxWidth: "var(--spacing-max-content)" }}>
        <PageTransition>
        <h1 className="text-lg font-bold text-text-primary mb-6">Nueva Transacción</h1>

        <form
          onSubmit={handleSubmit(onSubmit)}
          className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-5 max-w-lg"
        >
          {/* Amount */}
          <Field id="amount" label="Monto" error={errors.amount?.message}>
            <Input
              type="number"
              step="0.01"
              {...register("amount")}
              placeholder="0.00"
            />
          </Field>

          {/* Currency */}
          <Field id="currency" label="Moneda" error={errors.currency?.message}>
            <Input
              type="text"
              maxLength={3}
              {...register("currency")}
              className="uppercase"
              placeholder="USD"
            />
          </Field>

          {/* Merchant Name */}
          <Field
            id="merchant_name"
            label="Comercio"
            error={errors.merchant_name?.message}
          >
            <Input
              type="text"
              {...register("merchant_name")}
              placeholder="Nombre del comercio"
            />
          </Field>

          {/* Merchant Category (optional) */}
          {/* The dimmed "(opcional)" span is gone: `Field`'s `label` is typed
              `string`, and passing a node means casting around a primitive this
              pass is not allowed to change. The accessible name is identical
              either way (a label's text is the sum of its descendants), so this
              costs styling, not meaning. Restoring it means widening
              `FieldProps["label"]` to ReactNode — a primitives change. */}
          <Field id="merchant_category" label="Categoría (opcional)">
            <Input
              type="text"
              {...register("merchant_category")}
              placeholder="Ej: retail, travel"
            />
          </Field>

          {/* Card Last 4 */}
          <Field id="card_last4" label="Últimos 4 dígitos" error={errors.card_last4?.message}>
            <Input
              type="text"
              maxLength={4}
              {...register("card_last4")}
              placeholder="1234"
            />
          </Field>

          {/* Submit.
              `type="submit"` is EXPLICIT and load-bearing: `Button` defaults to
              `type="button"`, so without it this control is inert inside the
              form — focusable, clickable, and doing nothing at all. That is the
              opposite of the bug this page shipped with (a live button that did
              nothing useful), but it is the same failure mode from the other
              direction, so it is pinned by a test.

              `loading` carries the pending state instead of swapping the label:
              DESIGN.md asks for a non-changing label so the button width does
              not shift mid-action, and "Procesando..." is a different string
              from "Crear Transacción" — a real layout jump on the one control
              the user is about to press. `loading` already implies `disabled`. */}
          <Button
            type="submit"
            loading={mutation.isPending}
            disabled={!isValid}
            className="w-full"
          >
            Crear Transacción
          </Button>
        </form>

        {/* Score Result */}
            <ScoreResultCard result={result} isLoading={mutation.isPending} />
        </PageTransition>
      </div>
    </div>
  );
}
