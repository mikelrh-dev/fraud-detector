import { Toaster as SonnerToaster } from "sonner";

/**
 * Toast surface colors reference the @theme tokens via CSS variables —
 * no inline hex. (Sonner accepts any CSS color value, including var().)
 */
export function Toaster() {
  return (
    <SonnerToaster
      position="top-right"
      theme="dark"
      toastOptions={{
        style: {
          background: "var(--color-page-bg)",
          color: "var(--color-text-primary)",
          border: "1px solid var(--color-border-subtle)",
        },
        className: "font-sans",
      }}
    />
  );
}
