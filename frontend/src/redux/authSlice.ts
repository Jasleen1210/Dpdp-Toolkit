import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";

type User = {
  id: string;
  email: string;
  name: string;
};

export type OrganisationCredential = {
  id: string;
  name: string;
  role?: string;
  invite_code?: string;
  device_enrollment_code?: string;
  agent_token?: string;
  admin_api_key?: string;
};

type LoginPayload = {
  email: string;
  password: string;
};

type SignupPayload = {
  email: string;
  password: string;
  name: string;
};

type LoginResponse = {
  token: string;
  user: User;
  organisations?: OrganisationCredential[];
};

type SignupResponse = {
  user: User;
};

type AuthState = {
  token: string | null;
  user: User | null;
  organisations: OrganisationCredential[];
  loading: boolean;
  error: string | null;
  mode: "guest" | "user" | null;
};

const API_BASE = (
  (import.meta.env.VITE_API_URL as string | undefined) || ""
).replace(/\/$/, "");

function readStoredOrganisations(): OrganisationCredential[] {
  const raw = localStorage.getItem("auth_organisations");
  if (!raw) return [];

  try {
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? (parsed as OrganisationCredential[]) : [];
  } catch {
    return [];
  }
}

const initialState: AuthState = {
  token: localStorage.getItem("auth_token"),
  user: null,
  organisations: readStoredOrganisations(),
  loading: false,
  error: null,
  mode: (localStorage.getItem("auth_mode") as "guest" | "user" | null) || null,
};

async function readResponse<T>(
  res: Response,
): Promise<T | { detail?: string }> {
  const text = await res.text();
  if (!text) return {};
  try {
    return JSON.parse(text) as T;
  } catch {
    return { detail: text };
  }
}

export const loginUser = createAsyncThunk(
  "auth/loginUser",
  async (payload: LoginPayload, { rejectWithValue }) => {
    if (!API_BASE) {
      return rejectWithValue("VITE_API_URL is required");
    }

    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await readResponse<LoginResponse>(res);
    if (!res.ok) {
      return rejectWithValue(
        (data as { detail?: string }).detail || "Login failed",
      );
    }

    return data as LoginResponse;
  },
);

export const signupUser = createAsyncThunk(
  "auth/signupUser",
  async (payload: SignupPayload, { rejectWithValue }) => {
    if (!API_BASE) {
      return rejectWithValue("VITE_API_URL is required");
    }

    const res = await fetch(`${API_BASE}/auth/signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await readResponse<SignupResponse>(res);
    if (!res.ok) {
      return rejectWithValue(
        (data as { detail?: string }).detail || "Signup failed",
      );
    }

    return data as SignupResponse;
  },
);

export const logoutUser = createAsyncThunk(
  "auth/logoutUser",
  async (_, { getState, rejectWithValue }) => {
    if (!API_BASE) {
      return rejectWithValue("VITE_API_URL is required");
    }

    const state = getState() as { auth: AuthState };
    if (state.auth.mode === "guest") {
      return { ok: true };
    }

    const token = state.auth.token || localStorage.getItem("auth_token");

    if (!token) {
      return { ok: true };
    }

    const res = await fetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
    });

    if (!res.ok && res.status !== 401) {
      const text = await res.text();
      return rejectWithValue(text || "Logout failed");
    }

    return { ok: true };
  },
);

const authSlice = createSlice({
  name: "auth",
  initialState,
  reducers: {
    setSession(state, action: { payload: { token: string; user: User } }) {
      state.token = action.payload.token;
      state.user = action.payload.user;
      state.organisations = [];
      state.error = null;
      state.mode = "user";
      localStorage.setItem("auth_token", action.payload.token);
      localStorage.setItem("auth_mode", "user");
      localStorage.setItem("auth_organisations", JSON.stringify([]));
    },
    clearSession(state) {
      state.token = null;
      state.user = null;
      state.organisations = [];
      state.error = null;
      state.mode = null;
      localStorage.removeItem("auth_token");
      localStorage.removeItem("auth_mode");
      localStorage.removeItem("auth_organisations");
    },
    signInAsGuest(state) {
      state.token = `guest_${Date.now()}`;
      state.user = {
        id: "guest",
        email: "guest@local",
        name: "Guest User",
      };
      state.organisations = [];
      state.error = null;
      state.mode = "guest";
      localStorage.setItem("auth_token", state.token);
      localStorage.setItem("auth_mode", "guest");
      localStorage.setItem("auth_organisations", JSON.stringify([]));
    },
    setOrganisations(state, action: { payload: OrganisationCredential[] }) {
      state.organisations = action.payload;
      localStorage.setItem(
        "auth_organisations",
        JSON.stringify(action.payload),
      );
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(loginUser.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(loginUser.fulfilled, (state, action) => {
        state.loading = false;
        state.token = action.payload.token;
        state.user = action.payload.user;
        state.organisations = action.payload.organisations || [];
        state.mode = "user";
        localStorage.setItem("auth_token", action.payload.token);
        localStorage.setItem("auth_mode", "user");
        localStorage.setItem(
          "auth_organisations",
          JSON.stringify(action.payload.organisations || []),
        );
      })
      .addCase(loginUser.rejected, (state, action) => {
        state.loading = false;
        state.error =
          (action.payload as string) || action.error.message || "Login failed";
      })
      .addCase(signupUser.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(signupUser.fulfilled, (state) => {
        state.loading = false;
      })
      .addCase(signupUser.rejected, (state, action) => {
        state.loading = false;
        state.error =
          (action.payload as string) || action.error.message || "Signup failed";
      })
      .addCase(logoutUser.pending, (state) => {
        state.loading = true;
      })
      .addCase(logoutUser.fulfilled, (state) => {
        state.loading = false;
        state.token = null;
        state.user = null;
        state.organisations = [];
        state.error = null;
        state.mode = null;
        localStorage.removeItem("auth_token");
        localStorage.removeItem("auth_mode");
        localStorage.removeItem("auth_organisations");
      })
      .addCase(logoutUser.rejected, (state, action) => {
        state.loading = false;
        state.error =
          (action.payload as string) || action.error.message || "Logout failed";
      });
  },
});

export const { setSession, clearSession, signInAsGuest, setOrganisations } =
  authSlice.actions;
export default authSlice.reducer;
