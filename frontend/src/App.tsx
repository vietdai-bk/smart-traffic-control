import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { Empty, Spinner } from "./components/ui/primitives";
import { useAuth } from "./context/AuthContext";
import { LiveProvider } from "./context/LiveContext";
import type { Perm } from "./lib/permissions";
import LoginPage from "./pages/LoginPage";
import CommandCenterPage from "./pages/CommandCenterPage";

const AnalyticsPage = lazy(() => import("./pages/AnalyticsPage"));
const AlertsPage = lazy(() => import("./pages/AlertsPage"));
const ConfigPage = lazy(() => import("./pages/ConfigPage"));
const UsersAuditPage = lazy(() => import("./pages/UsersAuditPage"));
const AssistantPage = lazy(() => import("./pages/AssistantPage"));

function Guard({ perms, children }: { perms: Perm[]; children: ReactNode }) {
  const { can } = useAuth();
  if (!perms.some((p) => can(p))) {
    return <Empty title="Bạn không có quyền truy cập khu vực này" hint="Liên hệ Quản trị viên để được cấp quyền phù hợp." />;
  }
  return <Suspense fallback={<Spinner />}>{children}</Suspense>;
}

function Protected() {
  const { user, ready } = useAuth();
  const loc = useLocation();
  if (!ready) return <Spinner label="Đang khôi phục phiên đăng nhập…" />;
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  return (
    <LiveProvider>
      <AppShell />
    </LiveProvider>
  );
}

function Home() {
  const { can } = useAuth();
  return <Navigate to={can("live:view") ? "/live" : "/analytics"} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Protected />}>
        <Route index element={<Home />} />
        <Route path="/live" element={<Guard perms={["live:view"]}><CommandCenterPage /></Guard>} />
        <Route path="/analytics" element={<Guard perms={["stats:view"]}><AnalyticsPage /></Guard>} />
        <Route path="/assistant" element={<Guard perms={["assistant:use"]}><AssistantPage /></Guard>} />
        <Route path="/alerts" element={<Guard perms={["alerts:view"]}><AlertsPage /></Guard>} />
        <Route path="/config" element={<Guard perms={["config:view"]}><ConfigPage /></Guard>} />
        <Route path="/admin" element={<Guard perms={["users:manage", "audit:view"]}><UsersAuditPage /></Guard>} />
        <Route path="*" element={<Home />} />
      </Route>
    </Routes>
  );
}
