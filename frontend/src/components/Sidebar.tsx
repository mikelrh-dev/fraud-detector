import { useLocation, useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/authStore";

interface SidebarProps {
  activeItem: "dashboard" | "transactions" | "alerts";
}

interface NavItemProps {
  icon: string;
  label: string;
  isActive: boolean;
  onClick: () => void;
}

interface UserSectionProps {
  user: { id: string; role: string } | null;
  onLogout: () => void;
}

const navItems = [
  { key: "dashboard" as const, label: "Dashboard", icon: "dashboard", path: "/dashboard" },
  { key: "transactions" as const, label: "Transacciones", icon: "payments", path: "/transactions" },
  { key: "alerts" as const, label: "Alertas", icon: "notifications_active", path: "/alerts" },
];

function NavItem({ icon, label, isActive, onClick }: NavItemProps) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
        isActive
          ? "bg-slate-800 text-slate-200"
          : "text-slate-400 hover:bg-slate-800/50 hover:text-slate-300"
      }`}
    >
      <span className="material-symbols-outlined text-base">{icon}</span>
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
        className="w-full flex items-center gap-2 text-xs text-slate-500 hover:text-red-400 transition-colors py-1"
      >
        <span className="material-symbols-outlined text-base">logout</span>
        Cerrar sesión
      </button>
    </div>
  );
}

export function Sidebar({ activeItem }: SidebarProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuthStore();

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  const isActive = (key: string) => {
    if (key === activeItem) return true;
    if (key === "transactions" && location.pathname.startsWith("/transactions")) return true;
    return false;
  };

  return (
    <aside className="w-sidebar-width bg-slate-900 border-r border-slate-800 flex flex-col flex-shrink-0 min-h-screen">
      {/* Brand */}
      <div className="p-4 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-red-400 text-xl">shield</span>
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
            onClick={() => navigate(item.path)}
          />
        ))}
      </nav>

      {/* User info */}
      <UserSection user={user} onLogout={handleLogout} />
    </aside>
  );
}
