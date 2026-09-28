import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { Eye, EyeSlash } from "@phosphor-icons/react";
import { register } from "../api/auth";
import { AUTH_INPUT_CLASS, AuthSplitLayout } from "../components/AuthSplitLayout";
import { Button } from "../components/Button";
import { BTN_BASE, BTN_SIZES, BTN_VARIANTS, cn } from "../lib/ui";


const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const USERNAME_MIN = 3;
const USERNAME_MAX = 100;
const PASSWORD_MIN = 8;

type StrengthLevel = "weak" | "medium" | "strong";

/**
 * Segmented meter config: `segments` = filled count of the 3-segment track,
 * tone rides the shared risk tokens (critical / warn / clean).
 */
const STRENGTH_CONFIG: Record<
  StrengthLevel,
  { label: string; segments: number; segmentClass: string; textClass: string }
> = {
  weak: {
    label: "Débil",
    segments: 1,
    segmentClass: "bg-risk-critical",
    textClass: "text-risk-critical",
  },
  medium: {
    label: "Media",
    segments: 2,
    segmentClass: "bg-risk-warn",
    textClass: "text-risk-warn",
  },
  strong: {
    label: "Fuerte",
    segments: 3,
    segmentClass: "bg-risk-clean",
    textClass: "text-risk-clean",
  },
};

const SEGMENT_COUNT = 3;

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
  const [showPassword, setShowPassword] = useState(false);
  // Self-service registration is always analyst — the API rejects any other
  // role (audit R1-001), so no role selector is rendered.
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
      setError(`La contraseña debe tener al menos ${PASSWORD_MIN} caracteres.`);
      return;
    }

    setLoading(true);

    try {
      await register({
        username: username.trim(),
        email,
        password,
        role: "analyst",
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
    <AuthSplitLayout>
      <h1 className="text-2xl font-semibold tracking-tight text-slate-100">
        Crear cuenta
      </h1>
      <p className="mt-1 text-sm text-slate-500">
        Registrá un nuevo perfil de analista
      </p>

      {success ? (
        <div className="mt-8 space-y-4">
          <div className="rounded-lg bg-risk-clean/10 border border-risk-clean/30 px-3 py-4 text-sm text-risk-clean">
            <p className="font-medium">Cuenta creada exitosamente.</p>
            <p className="mt-1 text-risk-clean/80">
              Ya puede iniciar sesión con su email y contraseña.
            </p>
          </div>
          {/* A navigation control, so it stays a `<Link>` and takes the shared
              class constants rather than the `Button` component — `Button`
              renders a `<button>`, and a link that pretends to be a button
              loses middle-click, ctrl-click and "open in new tab", plus the
              status-bar URL. Composing the constants is what DESIGN.md's
              Buttons section prescribes ("All buttons compose from the shared
              constants in src/lib/ui.ts ... via cn()"), and it is what lets
              this pick up the shared focus ring and the `enabled:` hover gate
              it was missing. A real `ButtonLink` is the honest primitive here;
              it is reported, not invented here. */}
          <Link
            to="/login"
            className={cn(
              BTN_BASE,
              BTN_VARIANTS.primary,
              BTN_SIZES.md,
              "h-11 w-full",
            )}
          >
            Volver a Login
          </Link>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="mt-8 space-y-4" noValidate>
          {/* The three inputs are NOT on `Input`/`Field`, for the same reason
              and with the same consequences as on `LoginPage`: DESIGN.md gives
              the auth split-screen its own field spec (`text-xs` slate-400
              labels, `h-11` inputs, a risk-critical/25 focus ring), five
              deliberate departures from `INPUT_BASE`/`FIELD_LABEL` that
              `className` cannot bridge, because Tailwind decides between two
              utilities of the same property by stylesheet order rather than
              attribute order. See LoginPage.tsx for the full argument and for
              what this costs: the hand-rolled `focus:` ring that paints on
              mouse click, and label/error wiring that is visually adjacent
              rather than programmatically associated.

              The strength meter below the password field stays too — it is not
              a form control and has no primitive. */}
          <div>
            <label
              htmlFor="username"
              className="mb-1.5 block text-xs font-medium text-slate-400"
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
              className={AUTH_INPUT_CLASS}
            />
          </div>

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
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Mínimo 8 caracteres"
                required
                minLength={PASSWORD_MIN}
                className={`${AUTH_INPUT_CLASS} pr-11`}
              />
              {/* Unmigrated for the same reason as on `LoginPage`: no
                  icon-only size, and no variant whose resting and hover text
                  match `slate-500` → `slate-300`. `ghost` would change both
                  states; `secondary` would add a border and a background. */}
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

            {/* Segmented strength indicator */}
            {password.length > 0 && (
              <div className="mt-2" role="status" aria-live="polite" data-testid="password-strength">
                <div className="flex gap-1">
                  {Array.from({ length: SEGMENT_COUNT }, (_, i) => (
                    <span
                      key={i}
                      className={`h-1 flex-1 rounded-full ${
                        i < strengthConfig.segments
                          ? strengthConfig.segmentClass
                          : "bg-slate-700/50"
                      }`}
                    />
                  ))}
                </div>
                <p className={`mt-1.5 text-xs ${strengthConfig.textClass}`}>
                  Fortaleza: {strengthConfig.label}
                </p>
              </div>
            )}
          </div>

          {/* Reserved error line — rendered only when the form has an error */}
          {error && (
            <p role="alert" className="text-xs text-risk-critical mt-1.5">
              {error}
            </p>
          )}

          {/* Submit. `type="submit"` is EXPLICIT and load-bearing: `Button`
              defaults to `type="button"`, so without it this control is inert
              inside the form — focusable, clickable, and doing nothing.

              `loading` is deliberately not used, matching `LoginPage`: it
              would replace the reviewed "Creando cuenta..." copy with a
              spinner, which is a visible change on the control the user is
              about to press. `disabled` carries the pending state as before.

              DELTA, the same one as on `LoginPage` and the only visual one
              here: the hand-rolled `disabled:bg-red-800/50` becomes
              `BTN_BASE`'s `disabled:opacity-50`. Not an equivalent swap —
              `bg`/50 only set `background-color`, so the old pending state
              kept its label at full strength, while `opacity-50` applies to
              the whole element and dims the label too. Same signal, and the
              accent instead of red-800, but the text changes with it. */}
          <Button
            type="submit"
            variant="primary"
            disabled={loading}
            className="h-11 w-full"
          >
            {loading ? "Creando cuenta..." : "Crear Cuenta"}
          </Button>
        </form>
      )}

      {/* Back to login */}
      <p className="mt-6 text-center text-sm text-slate-500">
        ¿Ya tiene cuenta?{" "}
        <Link
          to="/login"
          className="font-medium text-slate-400 hover:text-slate-200 underline-offset-4 hover:underline transition-colors"
        >
          Volver a Login
        </Link>
      </p>
    </AuthSplitLayout>
  );
}
