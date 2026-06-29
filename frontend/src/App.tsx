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
import { IssueReporterProvider } from "./components/issues/IssueReporter";

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
import QueuePage from "./pages/QueuePage";
import AuditLogPage from "./pages/AuditLogPage";
import AdminPage from "./pages/AdminPage";
import SettingsPage from "./pages/SettingsPage";
import IssuesPage from "./pages/IssuesPage";
import IssueDetailPage from "./pages/IssueDetailPage";
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
const ExplorerBrands4gram = lazy(() => import("./pages/ExplorerBrands4gram"));
const ExplorerBrand4gramDetail = lazy(() => import("./pages/ExplorerBrand4gramDetail"));
const ExplorerBrands5gram = lazy(() => import("./pages/ExplorerBrands5gram"));
const ExplorerBrand5gramDetail = lazy(() => import("./pages/ExplorerBrand5gramDetail"));
const ExplorerBrandsLongForm = lazy(() => import("./pages/ExplorerBrandsLongForm"));
const ExplorerBrandLongFormDetail = lazy(() => import("./pages/ExplorerBrandLongFormDetail"));
const ExplorerPhones = lazy(() => import("./pages/ExplorerPhones"));
const ExplorerPhoneDetail = lazy(() => import("./pages/ExplorerPhoneDetail"));
const ExplorerAddresses = lazy(() => import("./pages/ExplorerAddresses"));
const ExplorerAddressDetail = lazy(() => import("./pages/ExplorerAddressDetail"));
const ExplorerAddressRoots = lazy(() => import("./pages/ExplorerAddressRoots"));
const ExplorerAddressRootDetail = lazy(() => import("./pages/ExplorerAddressRootDetail"));
const ExplorerAddressUnitDetail = lazy(() => import("./pages/ExplorerAddressUnitDetail"));
const ExplorerContacts = lazy(() => import("./pages/ExplorerContacts"));
const ExplorerContactDetail = lazy(() => import("./pages/ExplorerContactDetail"));
const ExplorerAutoGroups = lazy(() => import("./pages/ExplorerAutoGroups"));
const ExplorerAutoGroupsTuning = lazy(() => import("./pages/ExplorerAutoGroupsTuning"));
const ExplorerAutoGroupDetail = lazy(() => import("./pages/ExplorerAutoGroupDetail"));
const ExplorerConflicts = lazy(() => import("./pages/ExplorerConflicts"));
const TestLabPage = lazy(() => import("./pages/TestLabPage"));

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
            <IssueReporterProvider>
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
                  <Route path="/queue" element={<QueuePage />} />
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
                <Route path="/explorer/brands/4gram" element={<ExplorerBrands4gram />} />
                <Route path="/explorer/brands/4gram/:fourgram" element={<ExplorerBrand4gramDetail />} />
                <Route path="/explorer/brands/5gram" element={<ExplorerBrands5gram />} />
                <Route path="/explorer/brands/5gram/:fivegram" element={<ExplorerBrand5gramDetail />} />
                <Route path="/explorer/brands/long-form" element={<ExplorerBrandsLongForm />} />
                <Route path="/explorer/brands/long-form/:phrase" element={<ExplorerBrandLongFormDetail />} />
                <Route path="/explorer/phones" element={<ExplorerPhones />} />
                <Route path="/explorer/phones/:phone" element={<ExplorerPhoneDetail />} />
                <Route path="/explorer/addresses" element={<Navigate to="/explorer/addresses/roots" replace />} />
                <Route path="/explorer/addresses/roots" element={<ExplorerAddressRoots />} />
                <Route path="/explorer/addresses/roots/:key" element={<ExplorerAddressRootDetail />} />
                <Route path="/explorer/addresses/bases" element={<ExplorerAddresses />} />
                <Route path="/explorer/addresses/bases/:key" element={<ExplorerAddressDetail />} />
                <Route path="/explorer/addresses/units/:key" element={<ExplorerAddressUnitDetail />} />
                <Route path="/explorer/contacts" element={<ExplorerContacts />} />
                <Route path="/explorer/contacts/:fingerprint" element={<ExplorerContactDetail />} />
                <Route path="/explorer/auto-groups" element={<ExplorerAutoGroups />} />
                <Route path="/explorer/auto-groups/tuning" element={<ExplorerAutoGroupsTuning />} />
                <Route path="/explorer/auto-groups/:id" element={<ExplorerAutoGroupDetail />} />
                <Route path="/explorer/conflicts" element={<ExplorerConflicts />} />
                <Route path="/labeling" element={<LabelingPage />} />
                <Route path="/labeling/audits/:slug" element={<LabelingAuditPage />} />
                <Route path="/labeling/sessions/:id" element={<LabelingSessionPage />} />
                <Route path="/test-lab" element={<TestLabPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  <Route path="/admin" element={<AdminPage />} />
                  <Route path="/issues" element={<IssuesPage />} />
                  <Route path="/issues/:id" element={<IssueDetailPage />} />
                </Route>
              </Routes>
            </Suspense>
            <CrmDrawer />
            <SourceViewerDrawer />
            <CommandPalette />
            </IssueReporterProvider>
          </BrowserRouter>
        </SourceViewerProvider>
        </CrmProvider>
      </AuthProvider>
    </Theme>
  );
}
