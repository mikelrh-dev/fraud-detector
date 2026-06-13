import { Toaster as SonnerToaster } from "sonner";

export function Toaster() {
  return (
    <SonnerToaster
      position="top-right"
      theme="dark"
      toastOptions={{
        style: {
          background: "#0f172a",
          color: "#f1f5f9",
          border: "1px solid #1e293b",
        },
        className: "font-body",
      }}
    />
  );
}
