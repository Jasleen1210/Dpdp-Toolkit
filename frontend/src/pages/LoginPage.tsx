import { FormEvent, useState } from "react";
import { Navigate } from "react-router-dom";
import { Moon, Sun } from "lucide-react";

import { useTheme } from "@/components/ThemeProvider";
import { Switch } from "@/components/ui/switch";
import { useAppDispatch, useAppSelector } from "@/redux/hooks";
import { loginUser, signInAsGuest, signupUser } from "@/redux/authSlice";

type Mode = "login" | "signup";

export default function LoginPage() {
  const dispatch = useAppDispatch();
  const { token, loading, error } = useAppSelector((state) => state.auth);
  const { theme, toggleTheme } = useTheme();

  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");

  if (token) {
    return <Navigate to="/" replace />;
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const email = username.trim();

    if (!email || !password) return;

    if (mode === "signup") {
      if (!name.trim()) return;
      const signupResult = await dispatch(
        signupUser({
          email,
          password,
          name: name.trim(),
        }),
      );

      if (signupUser.fulfilled.match(signupResult)) {
        await dispatch(
          loginUser({
            email,
            password,
          }),
        );
      }
      return;
    }

    await dispatch(
      loginUser({
        email,
        password,
      }),
    );
  };

  const handleGuestSignIn = async () => {
    await dispatch(signInAsGuest());
  };

  return (
    <div className="relative min-h-screen bg-muted/20 flex items-center justify-center p-6 overflow-hidden">
      <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(circle_at_top,rgba(59,130,246,0.10),transparent_40%),radial-gradient(circle_at_bottom_right,rgba(14,165,233,0.08),transparent_35%)]" />

      <form
        onSubmit={handleSubmit}
        className="relative w-full max-w-sm bg-card border border-border rounded-sm p-5 space-y-4 shadow-lg"
      >
        <div>
          <h1 className="text-lg font-semibold text-foreground">
            {mode === "login" ? "Login" : "Create account"}
          </h1>
          <p className="text-[12px] text-muted-foreground mt-1">
            {mode === "login"
              ? "Sign in with username and password."
              : "Create your account to join or create an organisation."}
          </p>
        </div>

        <div className="grid grid-cols-3 gap-2 text-[12px]">
          <button
            type="button"
            className={`h-8 rounded-sm border ${mode === "login" ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground"}`}
            onClick={() => setMode("login")}
          >
            Login
          </button>
          <button
            type="button"
            className={`h-8 rounded-sm border ${mode === "signup" ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground"}`}
            onClick={() => setMode("signup")}
          >
            Sign up
          </button>
          <button
            type="button"
            className="h-8 rounded-sm border border-border text-muted-foreground hover:bg-muted"
            onClick={handleGuestSignIn}
          >
            Guest
          </button>
        </div>

        {mode === "signup" ? (
          <label className="block text-[12px] text-foreground/90">
            Name
            <input
              className="mt-1 w-full h-9 px-3 text-[13px] bg-background border border-border rounded-sm focus:outline-none focus:ring-1 focus:ring-primary"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Your full name"
              autoComplete="name"
            />
          </label>
        ) : null}

        <label className="block text-[12px] text-foreground/90">
          Username
          <input
            className="mt-1 w-full h-9 px-3 text-[13px] bg-background border border-border rounded-sm focus:outline-none focus:ring-1 focus:ring-primary"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="you@example.com"
            autoComplete="username"
          />
        </label>

        <label className="block text-[12px] text-foreground/90">
          Password
          <input
            type="password"
            className="mt-1 w-full h-9 px-3 text-[13px] bg-background border border-border rounded-sm focus:outline-none focus:ring-1 focus:ring-primary"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="********"
          />
        </label>

        {error ? (
          <div className="rounded-sm border border-destructive/40 bg-destructive/10 px-3 py-2 text-[12px] text-destructive">
            {error}
          </div>
        ) : null}

        <button
          type="submit"
          disabled={loading}
          className="w-full h-9 rounded-sm bg-primary text-primary-foreground text-[13px] font-medium disabled:opacity-60"
        >
          {loading
            ? mode === "login"
              ? "Signing in..."
              : "Creating account..."
            : mode === "login"
              ? "Login"
              : "Sign up"}
        </button>
      </form>

      <div className="fixed bottom-4 left-4 z-20 flex items-center gap-2 rounded-sm border border-border bg-card/95 px-3 py-2 shadow-md">
        {theme === "light" ? (
          <Sun className="h-4 w-4 text-muted-foreground" />
        ) : (
          <Moon className="h-4 w-4 text-muted-foreground" />
        )}
        <span className="text-[12px] text-muted-foreground uppercase tracking-wider">
          {theme}
        </span>
        <Switch checked={theme === "dark"} onCheckedChange={toggleTheme} />
      </div>
    </div>
  );
}
