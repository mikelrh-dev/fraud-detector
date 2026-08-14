import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { register } from "../api/auth";

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const USERNAME_MIN = 3;
const USERNAME_MAX = 100;
const PASSWORD_MIN = 8;

type StrengthLevel = "weak" | "medium" | "strong";

const STRENGTH_CONFIG: Record<
  StrengthLevel,
  { label: string; barClass: string; widthClass: string; textClass: string }
> = {
  weak: {
    label: "Débil",
    barClass: "bg-red-500",
    widthClass: "w-1/3",
    textClass: "text-red-400",
  },
  medium: {
    label: "Media",
    barClass: "bg-yellow-500",
    widthClass: "w-2/3",
    textClass: "text-yellow-400",
  },
  strong: {
    label: "Fuerte",
    barClass: "bg-green-500",
    widthClass: "w-full",
    textClass: "text-green-400",
  },
};

/**
 * Password strength heuristic (frontend-only, not a policy):
 * - < 8 chars         -> weak
 * - 8-12 chars        -> medium
 * - > 12 chars with mixed case + a number -> strong
 * - > 12 chars without mixed case/numbers  -> medium
 */
function getPasswordStrength(password: string): StrengthLevel {
  if (password.length < PASSWORD_MIN) {
    return "weak";
  }
  const hasMixedCaseAndNumber =
    /[a-z]/.test(password) && /[A-Z]/.test(password) && /\d/.test(password);
  if (password.length > 12 && hasMixedCaseAndNumber) {
    return "strong";
  }
  return "medium";
}

export default function RegisterPage() {
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("analyst");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const strength = getPasswordStrength(password);
  const strengthConfig = STRENGTH_CONFIG[strength];

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (!EMAIL_REGEX.test(email)) {
      setError("Ingrese un email válido.");
      return;
    }

    if (
      username.trim().length < USERNAME_MIN ||
      username.trim().length > USERNAME_MAX
    ) {
      setError(
        `El nombre de usuario debe tener entre ${USERNAME_MIN} y ${USERNAME_MAX} caracteres.`,
      );
      return;
    }

    if (password.length < PASSWORD_MIN) {
      setError(
        `La contraseña debe tener al menos ${PASSWORD_MIN} caracteres.`,
      );
      return;
    }

    setLoading(true);

    try {
      await register({
        username: username.trim(),
        email,
        password,
        role,
      });
      setSuccess(true);
    } catch (err: unknown) {
      const axiosErr = err as {
        response?: { status?: number; data?: { detail?: unknown } };
      };
      if (axiosErr.response?.status === 409) {
        setError("Email ya registrado");
      } else if (typeof axiosErr.response?.data?.detail === "string") {
        setError(axiosErr.response.data.detail);
      } else {
        setError("Error de conexión. Intente nuevamente.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Logo / Title */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-red-900/30 border border-red-800/40 mb-4">
            <svg
              className="w-6 h-6 text-red-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z"
              />
            </svg>
          </div>
          <h1 className="text-xl font-bold text-slate-100">
            Fraud Detector
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Crear cuenta
          </p>
        </div>

        {/* Card */}
        <div className="bg-slate-900 rounded-xl border border-slate-800 p-6">
          {success ? (
            <div className="space-y-4">
              <div className="bg-green-900/20 border border-green-800/40 rounded-lg px-3 py-4 text-sm text-green-400">
                <p className="font-medium">Cuenta creada exitosamente.</p>
                <p className="mt-1 text-green-500/80">
                  Ya puede iniciar sesión con su email y contraseña.
                </p>
              </div>
              <Link
                to="/login"
                className="block w-full py-2 px-4 bg-red-600 hover:bg-red-500 text-white font-medium rounded-lg text-sm text-center transition-colors"
              >
                Volver a Login
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4" noValidate>
              <div>
                <label
                  htmlFor="username"
                  className="block text-sm font-medium text-slate-400 mb-1"
                >
                  Usuario
                </label>
                <input
                  id="username"
                  type="text"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Nombre de usuario"
                  required
                  minLength={USERNAME_MIN}
                  maxLength={USERNAME_MAX}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-red-500/40 focus:border-red-500/60 transition-colors"
                />
              </div>

              <div>
                <label
                  htmlFor="email"
                  className="block text-sm font-medium text-slate-400 mb-1"
                >
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Ingrese su email"
                  required
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-red-500/40 focus:border-red-500/60 transition-colors"
                />
              </div>

              <div>
                <label
                  htmlFor="password"
                  className="block text-sm font-medium text-slate-400 mb-1"
                >
                  Contraseña
                </label>
                <input
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Mínimo 8 caracteres"
                  required
                  minLength={PASSWORD_MIN}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-red-500/40 focus:border-red-500/60 transition-colors"
                />

                {/* Strength indicator */}
                {password.length > 0 && (
                  <div className="mt-2" role="status" aria-live="polite">
                    <div className="h-1.5 w-full bg-slate-700/50 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${strengthConfig.barClass} ${strengthConfig.widthClass}`}
                      />
                    </div>
                    <p className={`mt-1 text-xs ${strengthConfig.textClass}`}>
                      Fortaleza: {strengthConfig.label}
                    </p>
                  </div>
                )}
              </div>

              <div>
                <label
                  htmlFor="role"
                  className="block text-sm font-medium text-slate-400 mb-1"
                >
                  Rol
                </label>
                <select
                  id="role"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-red-500/40 focus:border-red-500/60 transition-colors"
                >
                  <option value="analyst">Analista</option>
                  <option value="admin">Administrador</option>
                </select>
              </div>

              {error && (
                <div className="bg-red-900/20 border border-red-800/40 rounded-lg px-3 py-2 text-sm text-red-400">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2 px-4 bg-red-600 hover:bg-red-500 disabled:bg-red-800/50 disabled:cursor-not-allowed text-white font-medium rounded-lg text-sm transition-colors"
              >
                {loading ? "Creando cuenta..." : "Crear Cuenta"}
              </button>
            </form>
          )}
        </div>

        {/* Back to login */}
        <p className="mt-6 text-center text-sm text-slate-500">
          ¿Ya tiene cuenta?{" "}
          <Link
            to="/login"
            className="text-red-400 hover:text-red-300 font-medium transition-colors"
          >
            Volver a Login
          </Link>
        </p>
      </div>
    </div>
  );
}