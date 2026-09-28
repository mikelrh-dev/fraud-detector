import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Eye, EyeSlash } from "@phosphor-icons/react";
import { login } from "../api/auth";
import { useAuthStore } from "../store/authStore";
import { AUTH_INPUT_CLASS, AuthSplitLayout } from "../components/AuthSplitLayout";
import { Button } from "../components/Button";

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
        {/* The two inputs below are NOT on `Input` + `Field`, deliberately.

            DESIGN.md gives the auth split-screen its own field spec — "RIGHT
            form panel: labels above inputs (`text-xs` slate-400); inputs per
            Forms spec (h-11, focus ring risk-critical/25)" — which is five
            deliberate departures from what the primitives carry: `bg-slate-900`
            against `INPUT_BASE`'s slate-800, `border-slate-800` against
            slate-700, `text-slate-200` against slate-100, `placeholder:text-
            slate-600` against slate-500, and a focus ring in the risk tone at
            25% against the full-strength `focus-ring` token. The label is the
            same story: `text-xs font-medium slate-400` against
            `FIELD_LABEL`'s `text-sm slate-300`.

            `Field` and `Input` expose no way to say "this surface's field
            spec is the other one", and passing the differences through
            `className` does not work either: Tailwind resolves two utilities
            of the same property by STYLESHEET ORDER, not attribute order, and
            the built CSS puts `.bg-slate-800` (245) before `.bg-slate-900`
            (246) and `.px-3` (262) before `.px-2` (261). The override wins
            only when it happens to sort later, so half the tokens would
            apply and half would not — the caller would be writing classes that
            look right and silently do nothing.

            So these stay as they are, and this pass records the divergence
            instead of hiding it. Two consequences that are NOT resolved here:
            the hand-rolled `AUTH_INPUT_CLASS` keeps its `focus:` ring, which
            paints on mouse click (the defect `FOCUS_RING` exists to fix), and
            these two fields keep their own label/error wiring rather than the
            programmatic `aria-describedby` link `Field` provides. Both are
            owed to the visual/design pass, which is the only place that can
            decide whether the auth panel keeps its own field spec.
        */}
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
            {/* The visibility toggle is NOT on `Button` either, and this one is
                a gap in the design system rather than a divergence from it:
                there is no icon-only size, and no variant whose resting and
                hover text match. `ghost` is `text-slate-400` → slate-100 and
                this is slate-500 → slate-300, so adopting it would change
                both states; `secondary` would add a border and a background.

                A size that carries no padding is what this control actually
                wants (`w-11`, `inset-y-0`, icon only), and `BTN_SIZES` is
                `sm`/`md` — both of which set horizontal padding. Minting an
                `icon` size is a DESIGN change, so it is reported, not made. */}
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

        {/* Submit. `type="submit"` is EXPLICIT and load-bearing: `Button`
            defaults to `type="button"`, so without it this control is inert
            inside the form — focusable, clickable, and doing nothing.

            `loading` is deliberately NOT used, even though the primitive has
            it. `loading` implies a fixed label plus a spinner, and the
            "Ingresando..." copy is the existing, reviewed one; swapping it
            for a spinner would be a visible change on the control the user
            is about to press, which this pass must not make. `disabled`
            carries the pending state exactly as it did before.

            DELTA, and it is the only visual one on this control: the old
            class carried `disabled:bg-red-800/50`, a hand-rolled disabled
            fill. `BTN_BASE` dims with `disabled:opacity-50` instead, so the
            pending state is now the accent at half opacity rather than
            red-800 at half opacity. Same signal, different value, and it is
            what every other button in the product already does.

            `h-11 w-full` are layout, and the primitive does not supply them. */}
        <Button
          type="submit"
          variant="primary"
          disabled={loading}
          className="h-11 w-full"
        >
          {loading ? "Ingresando..." : "Ingresar"}
        </Button>
      </form>

      {/* Demo login */}
      <div className="mt-6">
        <div className="flex items-center gap-3">
          <span className="h-px flex-1 bg-slate-800" aria-hidden="true" />
          <span className="text-xs text-slate-600">o</span>
          <span className="h-px flex-1 bg-slate-800" aria-hidden="true" />
        </div>

        {/* The demo CTA is a clean fit for `secondary` and this one is
            exception-free. Every token it used to re-type is either carried by
            the variant or is a no-op: `border-slate-700`, `text-slate-300`,
            `rounded-lg` and `font-medium` all match, `disabled:opacity-50` was
            already there, and `bg-transparent` is new but describes what an
            unclassed button already rendered.

            Two deltas, both wins rather than changes of appearance:
            `hover:bg-slate-800` became `enabled:hover:bg-slate-800`, so the
            fill no longer fires under the cursor while the control is
            disabled; and the control gains the shared `focus-visible` ring,
            replacing whatever the user agent drew for it. */}
        <Button
          variant="secondary"
          onClick={handleDemoLogin}
          disabled={loading}
          className="mt-4 h-11 w-full"
        >
          Demo: Probar con Cuenta de Prueba
        </Button>
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
