import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { createTransaction } from "../api/transactions";
import type { CreateTransactionRequest, ScoreResponse } from "../api/transactions";
import type { UseMutationResult } from "@tanstack/react-query";
import type { AxiosError } from "axios";

type ErrorResponse = { detail?: string };

export function useCreateTransaction(): UseMutationResult<
  ScoreResponse,
  Error,
  CreateTransactionRequest
> {
  return useMutation({
    mutationFn: (data: CreateTransactionRequest) => createTransaction(data),
    onError: (err) => {
      const axiosErr = err as AxiosError<ErrorResponse>;
      const message =
        axiosErr.response?.data?.detail || "Error al crear transacción";
      toast.error(message);
    },
  });
}
