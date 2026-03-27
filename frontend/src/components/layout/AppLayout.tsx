import { Navigate, Outlet, useLocation } from "react-router-dom";
import Sidebar from "./Sidebar";
import Header from "./Header";

const FULL_BLEED_ROUTES = ["/map"];

export default function AppLayout() {
  const location = useLocation();
  const token = localStorage.getItem("cleo_token");
  if (!token) return <Navigate to="/login" />;

  const isFullBleed = FULL_BLEED_ROUTES.some((r) => location.pathname.startsWith(r));

  return (
    <div className="app-layout">
      <Sidebar />
      <Header />
      <div className="app-main">
        <div className={isFullBleed ? "page-full-bleed" : "app-main-content"}>
          <Outlet />
        </div>
      </div>
    </div>
  );
}
