import { useState, useCallback, lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Theme, Text } from "@radix-ui/themes";
import { AuthContext, type User } from "./hooks/useAuth";
import { postApi } from "./api/client";

// Layout
import AppLayout from "./components/layout/AppLayout";
import LoginPage from "./components/auth/LoginPage";

// CRM
import { CrmProvider } from "./components/crm/CrmContext";
import CrmDrawer from "./components/crm/CrmDrawer";
import CommandPalette from "./components/ui/CommandPalette";

// Source Viewer
import { SourceViewerProvider } from "./components/source/SourceViewerContext";
import SourceViewerDrawer from "./components/source/SourceViewerDrawer";

// Pages
import DashboardPage from "./pages/DashboardPage";
import PropertiesPage from "./pages/PropertiesPage";
import PropertyDetailPage from "./pages/PropertyDetailPage";
import TransactionsPage from "./pages/TransactionsPage";
import TransactionDetailPage from "./pages/TransactionDetailPage";
import ContactsPage from "./pages/ContactsPage";
import ContactDetailPage from "./pages/ContactDetailPage";
import GroupsPage from "./pages/GroupsPage";
import GroupDetailPage from "./pages/GroupDetailPage";
import DealsPage from "./pages/DealsPage";
import DealDetailPage from "./pages/DealDetailPage";
import ListsPage from "./pages/ListsPage";
import ListDetailPage from "./pages/ListDetailPage";
import AuditLogPage from "./pages/AuditLogPage";
import AdminPage from "./pages/AdminPage";
import SettingsPage from "./pages/SettingsPage";
import OpportunitiesPage from "./pages/OpportunitiesPage";
import SellOpportunityDetailPage from "./pages/SellOpportunityDetailPage";
import BuyMandateDetailPage from "./pages/BuyMandateDetailPage";
import GroupComparePage from "./pages/GroupComparePage";
import DiscoveryPage from "./pages/DiscoveryPage";
import DiscoveryClusterPage from "./pages/DiscoveryClusterPage";

// Lazy-loaded pages
const MapPage = lazy(() => import("./pages/MapPage"));
const PipelineOverviewPage = lazy(() => import("./pages/PipelineOverviewPage"));
const PipelineStagePage = lazy(() => import("./pages/PipelineStagePage"));
const PipelineRecordPage = lazy(() => import("./pages/PipelineRecordPage"));
const PipelineTracePage = lazy(() => import("./pages/PipelineTracePage"));
const DataQualityPage = lazy(() => import("./pages/DataQualityPage"));
const LabelingPage = lazy(() => import("./pages/LabelingPage"));
const LabelingAuditPage = lazy(() => import("./pages/LabelingAuditPage"));
const LabelingSessionPage = lazy(() => import("./pages/LabelingSessionPage"));
const ExplorerBrandsUnigram = lazy(() => import("./pages/ExplorerBrandsUnigram"));
const ExplorerBrandUnigramDetail = lazy(() => import("./pages/ExplorerBrandUnigramDetail"));
const ExplorerBrandsBigram = lazy(() => import("./pages/ExplorerBrandsBigram"));
const ExplorerBrandBigramDetail = lazy(() => import("./pages/ExplorerBrandBigramDetail"));
const ExplorerBrandsTrigram = lazy(() => import("./pages/ExplorerBrandsTrigram"));
const ExplorerBrandTrigramDetail = lazy(() => import("./pages/ExplorerBrandTrigramDetail"));

// ============================================================
// Auth Provider
// ============================================================

function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    const saved = localStorage.getItem("cleo_user");
    return saved ? JSON.parse(saved) : null;
  });
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("cleo_token"));

  const login = useCallback(async (username: string, password: string) => {
    const data = await postApi<{ token: string; user: User }>("/auth/login", { username, password });
    localStorage.setItem("cleo_token", data.token);
    localStorage.setItem("cleo_user", JSON.stringify(data.user));
    setToken(data.token);
    setUser(data.user);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("cleo_token");
    localStorage.removeItem("cleo_user");
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, token, login, logout, isAuthenticated: !!token }}>
      {children}
    </AuthContext.Provider>
  );
}

// ============================================================
// App Router
// ============================================================

export default function App() {
  return (
    <Theme accentColor="jade" grayColor="slate" radius="medium" scaling="100%" appearance="light">
      <AuthProvider>
        <CrmProvider>
        <SourceViewerProvider>
          <BrowserRouter>
            <Suspense fallback={<div className="flex items-center justify-center h-screen"><Text>Loading...</Text></div>}>
              <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route element={<AppLayout />}>
                  <Route path="/" element={<DashboardPage />} />
                  <Route path="/properties" element={<PropertiesPage />} />
                  <Route path="/properties/:id" element={<PropertyDetailPage />} />
                  <Route path="/transactions" element={<TransactionsPage />} />
                  <Route path="/transactions/:sourceId" element={<TransactionDetailPage />} />
                  <Route path="/contacts" element={<ContactsPage />} />
                  <Route path="/contacts/:id" element={<ContactDetailPage />} />
                  <Route path="/groups" element={<GroupsPage />} />
                  <Route path="/groups/compare" element={<GroupComparePage />} />
                  <Route path="/groups/:id" element={<GroupDetailPage />} />
                  <Route path="/opportunities" element={<OpportunitiesPage />} />
                  <Route path="/opportunities/sell/:id" element={<SellOpportunityDetailPage />} />
                  <Route path="/opportunities/buy/:id" element={<BuyMandateDetailPage />} />
                  <Route path="/deals" element={<DealsPage />} />
                  <Route path="/deals/:id" element={<DealDetailPage />} />
                  <Route path="/lists" element={<ListsPage />} />
                  <Route path="/lists/:id" element={<ListDetailPage />} />
                  <Route path="/audit" element={<AuditLogPage />} />
                  <Route path="/map" element={<MapPage />} />
                <Route path="/pipeline" element={<PipelineOverviewPage />} />
                <Route path="/pipeline/trace/:rtId" element={<PipelineTracePage />} />
                <Route path="/pipeline/:stage" element={<PipelineStagePage />} />
                <Route path="/pipeline/:stage/*" element={<PipelineRecordPage />} />
                <Route path="/data-quality" element={<DataQualityPage />} />
                <Route path="/discovery" element={<DiscoveryPage />} />
                <Route path="/discovery/:clusterId" element={<DiscoveryClusterPage />} />
                <Route path="/explorer" element={<Navigate to="/explorer/brands/1gram" replace />} />
                <Route path="/explorer/brands" element={<Navigate to="/explorer/brands/1gram" replace />} />
                <Route path="/explorer/brands/1gram" element={<ExplorerBrandsUnigram />} />
                <Route path="/explorer/brands/1gram/:token" element={<ExplorerBrandUnigramDetail />} />
                <Route path="/explorer/brands/2gram" element={<ExplorerBrandsBigram />} />
                <Route path="/explorer/brands/2gram/:bigram" element={<ExplorerBrandBigramDetail />} />
                <Route path="/explorer/brands/3gram" element={<ExplorerBrandsTrigram />} />
                <Route path="/explorer/brands/3gram/:trigram" element={<ExplorerBrandTrigramDetail />} />
                <Route path="/labeling" element={<LabelingPage />} />
                <Route path="/labeling/audits/:slug" element={<LabelingAuditPage />} />
                <Route path="/labeling/sessions/:id" element={<LabelingSessionPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  <Route path="/admin" element={<AdminPage />} />
                </Route>
              </Routes>
            </Suspense>
            <CrmDrawer />
            <SourceViewerDrawer />
            <CommandPalette />
          </BrowserRouter>
        </SourceViewerProvider>
        </CrmProvider>
      </AuthProvider>
    </Theme>
  );
}
