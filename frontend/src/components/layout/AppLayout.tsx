import { useEffect, useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import Sidebar from "./Sidebar";
import Header from "./Header";
import AskClaudeDrawer from "../ai/AskClaudeDrawer";

const FULL_BLEED_ROUTES = ["/map", "/labeling/sessions/"];

export default function AppLayout() {
  const location = useLocation();
  const token = localStorage.getItem("cleo_token");
  const [askOpen, setAskOpen] = useState(false);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const meta = e.metaKey || e.ctrlKey;
      if (meta && e.key.toLowerCase() === "i") {
        e.preventDefault();
        setAskOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  if (!token) return <Navigate to="/login" />;

  const isFullBleed = FULL_BLEED_ROUTES.some((r) => location.pathname.startsWith(r));

  return (
    <div className="app-layout">
      <Sidebar />
      <Header onAskClaude={() => setAskOpen(true)} />
      <div className="app-main">
        <div className={isFullBleed ? "page-full-bleed" : "app-main-content"}>
          <Outlet />
        </div>
      </div>
      <AskClaudeDrawer open={askOpen} onClose={() => setAskOpen(false)} />
    </div>
  );
}
