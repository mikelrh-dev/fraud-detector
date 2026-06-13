import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useCreateTransaction } from "../hooks/useCreateTransaction";
import { ScoreResultCard } from "./ScoreResultCard";
import { useAuthStore } from "../store/authStore";
import { Sidebar } from "../components/Sidebar";
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
  user_id: z.string().min(1),
});

type TransactionFormData = z.infer<typeof transactionSchema>;

export default function CreateTransactionPage() {
  const [result, setResult] = useState<ScoreResponse | null>(null);
  const user = useAuthStore((s) => s.user);

  const {
    register,
    handleSubmit,
    formState: { errors, isValid },
  } = useForm<TransactionFormData>({
    resolver: zodResolver(transactionSchema),
    mode: "onChange",
    defaultValues: {
      user_id: user?.id || "",
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
    <div className="min-h-screen bg-page-bg flex">
      <Sidebar activeItem="transactions" />
      <div className="flex-1 p-6 overflow-y-auto" style={{ maxWidth: "var(--spacing-max-content)" }}>
        <h1 className="text-lg font-bold text-text-primary mb-6">Nueva Transacción</h1>

        <form
          onSubmit={handleSubmit(onSubmit)}
          className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-5 max-w-lg"
        >
          {/* Amount */}
          <div>
            <label htmlFor="amount" className="block text-sm text-slate-300 mb-1">
              Monto
            </label>
            <input
              id="amount"
              type="number"
              step="0.01"
              {...register("amount")}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-focus-ring"
              placeholder="0.00"
            />
            {errors.amount && (
              <p className="text-xs text-red-400 mt-1">{errors.amount.message}</p>
            )}
          </div>

          {/* Currency */}
          <div>
            <label htmlFor="currency" className="block text-sm text-slate-300 mb-1">
              Moneda
            </label>
            <input
              id="currency"
              type="text"
              maxLength={3}
              {...register("currency")}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-focus-ring uppercase"
              placeholder="USD"
            />
            {errors.currency && (
              <p className="text-xs text-red-400 mt-1">{errors.currency.message}</p>
            )}
          </div>

          {/* Merchant Name */}
          <div>
            <label htmlFor="merchant_name" className="block text-sm text-slate-300 mb-1">
              Comercio
            </label>
            <input
              id="merchant_name"
              type="text"
              {...register("merchant_name")}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-focus-ring"
              placeholder="Nombre del comercio"
            />
            {errors.merchant_name && (
              <p className="text-xs text-red-400 mt-1">{errors.merchant_name.message}</p>
            )}
          </div>

          {/* Merchant Category (optional) */}
          <div>
            <label htmlFor="merchant_category" className="block text-sm text-slate-300 mb-1">
              Categoría <span className="text-slate-500">(opcional)</span>
            </label>
            <input
              id="merchant_category"
              type="text"
              {...register("merchant_category")}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-focus-ring"
              placeholder="Ej: retail, travel"
            />
          </div>

          {/* Card Last 4 */}
          <div>
            <label htmlFor="card_last4" className="block text-sm text-slate-300 mb-1">
              Últimos 4 dígitos
            </label>
            <input
              id="card_last4"
              type="text"
              maxLength={4}
              {...register("card_last4")}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-focus-ring"
              placeholder="1234"
            />
            {errors.card_last4 && (
              <p className="text-xs text-red-400 mt-1">{errors.card_last4.message}</p>
            )}
          </div>

          {/* Hidden user_id */}
          <input type="hidden" {...register("user_id")} />

          {/* Submit */}
          <button
            type="submit"
            disabled={!isValid || mutation.isPending}
            className="w-full bg-primary-container hover:bg-action-hover disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium py-2.5 rounded-lg transition-colors"
          >
            {mutation.isPending ? "Procesando..." : "Crear Transacción"}
          </button>
        </form>

        {/* Score Result */}
        <ScoreResultCard result={result} isLoading={mutation.isPending && result === null} />
      </div>
    </div>
  );
}
