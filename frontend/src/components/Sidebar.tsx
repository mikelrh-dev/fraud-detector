import { useState, useEffect } from "react";
import type { ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { BellRinging, List, Receipt, SignOut, SquaresFour } from "@phosphor-icons/react";
import { useAuthStore } from "../store/authStore";
import { BrandShield } from "./BrandShield";

interface SidebarProps {
  activeItem: "dashboard" | "transactions" | "alerts";
}

interface NavItemProps {
  icon: ReactNode;
  label: string;
  isActive: boolean;
  onClick: () => void;
}

interface UserSectionProps {
  user: { id: string; role: string } | null;
  onLogout: () => void;
}

const navItems = [
  { key: "dashboard" as const, label: "Dashboard", icon: <SquaresFour size={16} />, path: "/dashboard" },
  { key: "transactions" as const, label: "Transacciones", icon: <Receipt size={16} />, path: "/transactions" },
  { key: "alerts" as const, label: "Alertas", icon: <BellRinging size={16} />, path: "/alerts" },
];

function NavItem({ icon, label, isActive, onClick }: NavItemProps) {
  return (
    // aria-current drives the sliding 2px indicator (pure CSS — see
    // .nav-indicator in index.css); no JS measuring, no layout animation.
    <button
      onClick={onClick}
      aria-current={isActive ? "page" : undefined}
      className={`nav-item relative w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
        isActive
          ? "bg-slate-800 text-slate-200"
          : "text-slate-400 hover:bg-slate-800/50 hover:text-slate-300"
      }`}
    >
      <span aria-hidden="true" className="nav-indicator" />
      {icon}
      {label}
    </button>
  );
}

function UserSection({ user, onLogout }: UserSectionProps) {
  const avatarInitials = user?.id?.slice(0, 2).toUpperCase() || "?";
  const userIdTruncated = user?.id?.slice(0, 8) || "—";
  const userRole = user?.role || "Analista";

  return (
    <div className="p-3 border-t border-slate-800">
      <div className="flex items-center gap-2 mb-2">
        <div className="w-7 h-7 rounded-full bg-slate-700 flex items-center justify-center text-xs text-slate-300 font-medium">
          {avatarInitials}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs text-slate-300 truncate">{userRole}</p>
          <p className="text-[10px] text-slate-500">ID: {userIdTruncated}</p>
        </div>
      </div>
      <button
        onClick={onLogout}
        className="w-full flex items-center gap-2 text-xs text-slate-500 hover:text-risk-critical transition-colors py-1"
      >
        <SignOut size={16} aria-hidden="true" />
        Cerrar sesión
      </button>
    </div>
  );
}

export function Sidebar({ activeItem }: SidebarProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuthStore();
  const [open, setOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  const isActive = (key: string) => {
    if (key === activeItem) return true;
    if (key === "transactions" && location.pathname.startsWith("/transactions")) return true;
    return false;
  };

  // Escape key closes drawer
  useEffect(() => {
    if (!open) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [open]);

  // Body scroll lock when drawer is open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  const sidebarContent = (
    <>
      {/* Brand */}
      <div className="p-4 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <BrandShield className="h-5 w-5 text-accent" />
          <span className="text-sm font-bold text-slate-100">Fraud Detector</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-3 space-y-1">
        {navItems.map((item) => (
          <NavItem
            key={item.key}
            icon={item.icon}
            label={item.label}
            isActive={isActive(item.key)}
            onClick={() => {
              navigate(item.path);
              setOpen(false);
            }}
          />
        ))}
      </nav>

      {/* User info */}
      <UserSection user={user} onLogout={handleLogout} />
    </>
  );

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden md:flex w-sidebar-width bg-slate-900 border-r border-slate-800 flex-col flex-shrink-0 min-h-screen">
        {sidebarContent}
      </aside>

      {/* Mobile burger button.

          The touch floor is UNCONDITIONAL here, and the difference from the
          other icon-only controls is structural rather than a second opinion:
          this one is `md:hidden`, so it exists only below the breakpoint where
          the house `max-md:` floor applies. Writing `max-md:min-h-[40px]` would
          be true for every pixel it is ever visible, and true-but-constant is
          what a `max-md:` prefix is for nothing.

          `p-2` around a 20px glyph is 36x36, so BOTH axes are under the floor
          and both are raised. The glyph stays at 20 — the button box grew, the
          icon did not. */}
      <button
        onClick={() => setOpen(true)}
        className="md:hidden fixed top-4 left-4 z-50 p-2 min-h-[40px] min-w-[40px] inline-flex items-center justify-center rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 transition-colors"
        aria-expanded={open}
        aria-label="Abrir menú de navegación"
      >
        <List size={20} aria-hidden="true" />
      </button>

      {/* Mobile drawer */}
      {open && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/60 z-[55]"
            onClick={() => setOpen(false)}
          />
          {/* Drawer panel */}
          <aside
            className="fixed inset-y-0 left-0 z-[60] w-[224px] bg-slate-900 border-r border-slate-800 flex flex-col"
            role="dialog"
            aria-modal="true"
            aria-label="Menú de navegación"
          >
            {sidebarContent}
          </aside>
        </>
      )}
    </>
  );
}
