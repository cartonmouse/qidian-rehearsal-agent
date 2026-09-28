import { type ReactNode } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AuthProvider } from "./contexts/AuthContext";
import useAuth from "./hooks/useAuth";
import Sidebar from "./components/Sidebar";
import ComplianceFooter from "./components/ComplianceFooter";
import ErrorBoundary from "./components/ErrorBoundary";
import Login from "./pages/Login";
import Onboarding from "./pages/Onboarding";
import NotFound from "./pages/NotFound";
import RehearsalStudio from "./pages/RehearsalStudio";
import ScriptRag from "./pages/ScriptRag";
import ActorSchedule from "./pages/ActorSchedule";
import LineReading from "./pages/LineReading";
import RehearsalFeedback from "./pages/RehearsalFeedback";
import RehearsalMetrics from "./pages/RehearsalMetrics";
import RehearsalLogbook from "./pages/RehearsalLogbook";
import SuggestionInbox from "./pages/SuggestionInbox";
import KnowledgeAssets from "./pages/KnowledgeAssets";
import VersionTracking from "./pages/VersionTracking";
import StageVisualization from "./pages/StageVisualization";
import ResourceManagement from "./pages/ResourceManagement";
import ResourceFinance from "./pages/ResourceFinance";
import AgentRuns from "./pages/AgentRuns";

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { token, loading } = useAuth();
  if (loading) return null;
  if (!token) return <Navigate to="/" replace />;
  return children;
}

// Gate the app behind first-run provider setup: a user with no LLM/Embedding
// configured can't do anything useful, so funnel them through onboarding first.
function ProviderGate({ children }: { children: ReactNode }) {
  const { needsOnboarding } = useAuth();
  const location = useLocation();
  // 第一阶段的剧本解析节点是本地规则 Agent，不依赖 LLM/Embedding 配置；
  // 让它可以先被独立演示，其他需要模型服务的页面继续走原有引导。
  if (location.pathname.startsWith("/rehearsal")) return children;
  if (needsOnboarding) return <Onboarding />;
  return children;
}

function PublicHome() {
  const { token, loading } = useAuth();
  if (loading) return null;
  if (token) return <Navigate to="/rehearsal" replace />;
  return <Navigate to="/login" replace />;
}

function AuthPage() {
  const { token, loading } = useAuth();
  if (loading) return null;
  if (token) return <Navigate to="/rehearsal" replace />;
  return <Login />;
}

function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col md:flex-row h-screen">
      <Sidebar />
      <main className="flex-1 overflow-y-auto flex flex-col">
        {children}
        <ComplianceFooter />
      </main>
    </div>
  );
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<PublicHome />} />
      <Route path="/login" element={<AuthPage />} />
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <ProviderGate>
            <AppShell>
              <Routes>
                <Route path="/rehearsal" element={<RehearsalStudio />} />
                <Route path="/rehearsal/rag" element={<ScriptRag />} />
                <Route path="/rehearsal/schedule" element={<ActorSchedule />} />
                <Route path="/rehearsal/line-reading" element={<LineReading />} />
                <Route path="/rehearsal/feedback" element={<RehearsalFeedback />} />
                <Route path="/rehearsal/metrics" element={<RehearsalMetrics />} />
                <Route path="/rehearsal/logbook" element={<RehearsalLogbook />} />
                <Route path="/rehearsal/suggestions" element={<SuggestionInbox />} />
                <Route path="/rehearsal/knowledge" element={<KnowledgeAssets />} />
                <Route path="/rehearsal/versions" element={<VersionTracking />} />
                <Route path="/rehearsal/stage" element={<StageVisualization />} />
                <Route path="/rehearsal/resources" element={<ResourceManagement />} />
                <Route path="/rehearsal/resource-finance" element={<ResourceFinance />} />
                <Route path="/rehearsal/runs" element={<AgentRuns />} />
                <Route path="/settings" element={<Onboarding />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </AppShell>
            </ProviderGate>
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <ErrorBoundary>
          <AppRoutes />
        </ErrorBoundary>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
