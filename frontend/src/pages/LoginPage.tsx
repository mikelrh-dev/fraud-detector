import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Eye, EyeSlash } from "@phosphor-icons/react";
import { login } from "../api/auth";
import { useAuthStore } from "../store/authStore";
import { AUTH_INPUT_CLASS, AuthSplitLayout } from "../components/AuthSplitLayout";

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const DEMO_EMAIL = "admin@frauddetector.dev";
const DEMO_PASSWORD = "admin123";

export default function LoginPage() {
  const navigate = useNavigate();
  const storeLogin = useAuthStore((s) => s.login);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submitCredentials(credentials: {
    email: string;
    password: string;
  }) {
    setError(null);
    setLoading(true);

    try {
      const result = await login(credentials);
      storeLogin(result.access_token, result.refresh_token);
      navigate("/dashboard", { replace: true });
    } catch (err: unknown) {
      if (err && typeof err === "object" && "response" in err) {
        const axiosErr = err as {
          response?: { data?: { detail?: string } };
        };
        setError(
          axiosErr.response?.data?.detail || "Credenciales inválidas",
        );
      } else {
        setError("Error de conexión. Intente nuevamente.");
      }
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();

    if (!EMAIL_REGEX.test(email)) {
      setError("Ingrese un email válido.");
      return;
    }

    if (password.length === 0) {
      setError("Ingrese su contraseña.");
      return;
    }

    void submitCredentials({ email, password });
  }

  function handleDemoLogin() {
    setEmail(DEMO_EMAIL);
    setPassword(DEMO_PASSWORD);
    void submitCredentials({ email: DEMO_EMAIL, password: DEMO_PASSWORD });
  }

  return (
    <AuthSplitLayout>
      <h1 className="text-2xl font-semibold tracking-tight text-slate-100">
        Iniciar sesión
      </h1>
      <p className="mt-1 text-sm text-slate-500">
        Accede a la consola de análisis
      </p>

      <form onSubmit={handleSubmit} className="mt-8 space-y-4" noValidate>
        <div>
          <label
            htmlFor="email"
            className="mb-1.5 block text-xs font-medium text-slate-400"
          >
            Email
          </label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="tu@email.com"
            required
            className={AUTH_INPUT_CLASS}
          />
        </div>

        <div>
          <label
            htmlFor="password"
            className="mb-1.5 block text-xs font-medium text-slate-400"
          >
            Contraseña
          </label>
          <div className="relative">
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              className={`${AUTH_INPUT_CLASS} pr-11`}
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={
                showPassword ? "Ocultar contraseña" : "Mostrar contraseña"
              }
              aria-pressed={showPassword}
              className="btn-motion absolute inset-y-0 right-0 flex w-11 items-center justify-center text-slate-500 hover:text-slate-300"
            >
              {showPassword ? (
                <EyeSlash size={16} aria-hidden="true" />
              ) : (
                <Eye size={16} aria-hidden="true" />
              )}
            </button>
          </div>
        </div>

        {/* Reserved error line — rendered only when the form has an error */}
        {error && (
          <p role="alert" className="text-xs text-risk-critical mt-1.5">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading}
          className="btn-motion active:scale-[0.98] h-11 w-full rounded-lg bg-accent hover:bg-action-hover disabled:bg-red-800/50 disabled:cursor-not-allowed font-medium text-white text-sm"
        >
          {loading ? "Ingresando..." : "Ingresar"}
        </button>
      </form>

      {/* Demo login */}
      <div className="mt-6">
        <div className="flex items-center gap-3">
          <span className="h-px flex-1 bg-slate-800" aria-hidden="true" />
          <span className="text-xs text-slate-600">o</span>
          <span className="h-px flex-1 bg-slate-800" aria-hidden="true" />
        </div>

        <button
          type="button"
          onClick={handleDemoLogin}
          disabled={loading}
          className="btn-motion active:scale-[0.98] mt-4 h-11 w-full rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed font-medium text-sm"
        >
          Demo: Probar con Cuenta de Prueba
        </button>
      </div>

      {/* Register link */}
      <p className="mt-6 text-center text-sm text-slate-500">
        ¿Primera vez?{" "}
        <Link
          to="/register"
          className="font-medium text-slate-400 hover:text-slate-200 underline-offset-4 hover:underline transition-colors"
        >
          Crear cuenta aquí
        </Link>
      </p>
    </AuthSplitLayout>
  );
}
