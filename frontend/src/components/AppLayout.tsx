import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { NAV_ITEMS } from "@/lib/constants";
import { useTheme } from "@/components/ThemeProvider";
import {
  Menu,
  X,
  Search,
  Bell,
  User,
  Sun,
  Moon,
  ChevronDown,
  ChevronRight,
  Shield,
} from "lucide-react";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAppDispatch } from "@/redux/hooks";
import { logoutUser } from "@/redux/authSlice";
import { motion, AnimatePresence } from "framer-motion";

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const location = useLocation();
  const [expandedItem, setExpandedItem] = useState<string | null>(null);

  const parseHref = (href: string) => {
    const [pathname, search = ""] = href.split("?");
    return { pathname, search: search ? `?${search}` : "" };
  };

  const isActive = (href: string) => {
    const target = parseHref(href);
    if (target.search) {
      return (
        location.pathname === target.pathname &&
        location.search === target.search
      );
    }
    return location.pathname === target.pathname;
  };

  const isParentActive = (item: (typeof NAV_ITEMS)[0]) =>
    item.subtabs.some((s) => {
      const target = parseHref(s.href);
      return location.pathname === target.pathname;
    });

  return (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className="p-5 border-b border-sidebar-border">
        <Link to="/" className="flex items-center gap-2.5" onClick={onNavigate}>
          <div className="w-7 h-7 bg-primary rounded-sm flex items-center justify-center">
            <Shield className="w-4 h-4 text-primary-foreground" />
          </div>
          <span className="font-bold text-sm tracking-tight text-foreground">
            DPDP COMMAND
          </span>
        </Link>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-3 py-3 space-y-0.5">
        {NAV_ITEMS.map((item) => {
          const active = isParentActive(item);
          const expanded = expandedItem === item.label || active;

          return (
            <div key={item.label}>
              <button
                onClick={() =>
                  setExpandedItem(
                    expanded && expandedItem === item.label ? null : item.label,
                  )
                }
                className={`w-full flex items-center gap-2.5 px-3 py-2 text-[13px] font-medium rounded-sm transition-colors ${
                  active
                    ? "bg-sidebar-accent text-primary"
                    : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                }`}
              >
                <item.icon className="w-4 h-4 shrink-0" />
                <span className="flex-1 text-left">{item.label}</span>
                {expanded ? (
                  <ChevronDown className="w-3.5 h-3.5 opacity-50" />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5 opacity-50" />
                )}
              </button>

              <AnimatePresence>
                {expanded && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.15, ease: [0.2, 0.8, 0.2, 1] }}
                    className="overflow-hidden"
                  >
                    <div className="ml-5 pl-3 border-l border-sidebar-border space-y-0.5 py-1">
                      {item.subtabs.map((sub) => (
                        <Link
                          key={sub.href}
                          to={sub.href}
                          onClick={onNavigate}
                          className={`block px-3 py-1.5 text-[12px] rounded-sm transition-colors ${
                            isActive(sub.href)
                              ? "text-primary font-medium bg-sidebar-accent"
                              : "text-muted-foreground hover:text-foreground hover:bg-sidebar-accent"
                          }`}
                        >
                          {sub.label}
                        </Link>
                      ))}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </nav>

      {/* Theme Toggle */}
      <ThemeToggle />
    </div>
  );
}

function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  return (
    <div className="p-4 border-t border-sidebar-border">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
          {theme === "light" ? (
            <Sun className="w-3.5 h-3.5" />
          ) : (
            <Moon className="w-3.5 h-3.5" />
          )}
          <span className="uppercase tracking-wider">{theme} mode</span>
        </div>
        <Switch
          checked={theme === "dark"}
          onCheckedChange={toggleTheme}
          className="scale-75"
        />
      </div>
    </div>
  );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const handleLogout = async () => {
    await dispatch(logoutUser());
    navigate("/login", { replace: true });
  };

  return (
    <div className="min-h-screen flex w-full">
      {/* Desktop Sidebar */}
      <aside className="hidden lg:flex w-[240px] border-r border-border bg-sidebar flex-col h-screen sticky top-0 shrink-0">
        <SidebarContent />
      </aside>

      {/* Main area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Topbar */}
        <header className="h-12 border-b border-border bg-card flex items-center px-4 gap-3 sticky top-0 z-30">
          {/* Mobile hamburger */}
          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetTrigger asChild>
              <button
                className="lg:hidden p-1.5 rounded-sm hover:bg-muted"
                aria-label="Open menu"
              >
                <Menu className="w-5 h-5" />
              </button>
            </SheetTrigger>
            <SheetContent side="left" className="w-[260px] p-0">
              <SidebarContent onNavigate={() => setMobileOpen(false)} />
            </SheetContent>
          </Sheet>

          {/* Global Search */}
          <div className="flex-1 max-w-md mx-auto relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search users, Aadhaar, files, vendors..."
              className="w-full h-8 pl-8 pr-3 text-[13px] bg-muted/50 border border-border rounded-sm focus:outline-none focus:ring-1 focus:ring-primary placeholder:text-muted-foreground"
            />
          </div>

          {/* Right actions */}
          <div className="flex items-center gap-1">
            <button
              className="relative p-2 rounded-sm hover:bg-muted"
              aria-label="Notifications"
            >
              <Bell className="w-4 h-4 text-muted-foreground" />
              <span className="absolute top-1 right-1 w-2 h-2 bg-primary rounded-full" />
            </button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  className="p-2 rounded-sm hover:bg-muted"
                  aria-label="Profile"
                >
                  <User className="w-4 h-4 text-muted-foreground" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-40">
                <DropdownMenuItem asChild>
                  <Link to="/profile" className="w-full text-left">
                    Profile
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <Link to="/settings" className="w-full text-left">
                    Settings
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <button
                    type="button"
                    className="w-full text-left"
                    onClick={() => void handleLogout()}
                  >
                    Log out
                  </button>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-x-hidden">{children}</main>

        {/* Footer */}
        <AppFooter />
      </div>
    </div>
  );
}

function AppFooter() {
  return (
    <footer className="border-t border-border p-6 lg:p-8 bg-muted/30">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-6 lg:gap-8">
        <div>
          <h4 className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground mb-3">
            Product
          </h4>
          <ul className="space-y-1.5">
            {["About Platform", "Release Notes", "Roadmap"].map((l) => (
              <li key={l}>
                <a
                  href="#"
                  className="text-[12px] text-muted-foreground hover:text-foreground"
                >
                  {l}
                </a>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h4 className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground mb-3">
            Compliance
          </h4>
          <ul className="space-y-1.5">
            {[
              "DPDP Info",
              "Privacy Policy",
              "Terms of Service",
              "Security Certs (ISO, SOC2)",
            ].map((l) => (
              <li key={l}>
                <a
                  href="#"
                  className="text-[12px] text-muted-foreground hover:text-foreground"
                >
                  {l}
                </a>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h4 className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground mb-3">
            Support
          </h4>
          <ul className="space-y-1.5">
            {["Help Center", "API Docs", "Contact Support", "Status Page"].map(
              (l) => (
                <li key={l}>
                  <a
                    href="#"
                    className="text-[12px] text-muted-foreground hover:text-foreground"
                  >
                    {l}
                  </a>
                </li>
              ),
            )}
          </ul>
        </div>
        <div>
          <h4 className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground mb-3">
            Company
          </h4>
          <ul className="space-y-1.5">
            {["About", "Careers", "Blog"].map((l) => (
              <li key={l}>
                <a
                  href="#"
                  className="text-[12px] text-muted-foreground hover:text-foreground"
                >
                  {l}
                </a>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <div className="mt-8 pt-4 border-t border-border flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 text-system text-muted-foreground">
        <div>REGION: INDIA-SOUTH (KA-01)</div>
        <div className="flex gap-4">
          <span>V1.0.3-STABLE</span>
          <span className="text-primary">● SYSTEM_HEALTH_OK</span>
        </div>
      </div>
    </footer>
  );
}
