import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/components/ThemeProvider";
import AppLayout from "@/components/AppLayout";
import DashboardPage from "@/pages/DashboardPage";
import DataInventoryPage from "@/pages/DataInventoryPage";
import DataAccessPage from "@/pages/DataAccessPage";
import RequestsPage from "@/pages/RequestsPage";
import DataProtectionPage from "@/pages/DataProtectionPage";
import ConsentPage from "@/pages/ConsentPage";
import RetentionPage from "@/pages/RetentionPage";
import IncidentsPage from "@/pages/IncidentsPage";
import ThirdPartiesPage from "@/pages/ThirdPartiesPage";
import AuditPage from "@/pages/AuditPage";
import InfrastructurePage from "@/pages/InfrastructurePage";
import SettingsPage from "@/pages/SettingsPage";
import ProfilePage from "@/pages/ProfilePage";
import NotFound from "@/pages/NotFound";
import LoginPage from "@/pages/LoginPage";
import { useAppSelector } from "@/redux/hooks";

const queryClient = new QueryClient();

function AppRoutes() {
  const { token } = useAppSelector((state) => state.auth);
  const location = useLocation();
  const isLoginRoute = location.pathname === "/login";

  if (!token && !isLoginRoute) {
    return <Navigate to="/login" replace />;
  }

  if (token && isLoginRoute) {
    return <Navigate to="/" replace />;
  }

  if (isLoginRoute) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/dashboard/*" element={<DashboardPage />} />
        <Route path="/access-data/*" element={<DataAccessPage />} />
        <Route path="/data-inventory/*" element={<DataInventoryPage />} />
        <Route path="/requests/*" element={<RequestsPage />} />
        <Route path="/protection/*" element={<DataProtectionPage />} />
        <Route path="/consent/*" element={<ConsentPage />} />
        <Route path="/retention/*" element={<RetentionPage />} />
        <Route path="/incidents/*" element={<IncidentsPage />} />
        <Route path="/third-parties/*" element={<ThirdPartiesPage />} />
        <Route path="/audit/*" element={<AuditPage />} />
        <Route path="/infrastructure/*" element={<InfrastructurePage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/settings/*" element={<SettingsPage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </AppLayout>
  );
}

const App = () => (
  <ThemeProvider>
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </TooltipProvider>
    </QueryClientProvider>
  </ThemeProvider>
);

export default App;
