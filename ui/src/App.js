import { html, useEffect, useState } from "./vendor.js";
import { createMapsApiClient } from "./api/mapsApiClient.js";
import { Layout } from "./components/Layout.js";
import { matchRoute } from "./router.js";
import { MapsHomePage } from "./pages/MapsHome.js";
import { NavigationSignalsPage } from "./pages/NavigationSignals.js";
import { SignalDetailPage } from "./pages/SignalDetail.js";
import { RoutePredictionsPage } from "./pages/RoutePredictions.js";
import { HazardsPage } from "./pages/Hazards.js";
import { CongestionPage } from "./pages/Congestion.js";
import { CalibrationPage } from "./pages/Calibration.js";
import { RecommendationsPage } from "./pages/Recommendations.js";
import { StoryTypesPage } from "./pages/StoryTypes.js";
import { DocsPage } from "./pages/Docs.js";
import { WhitepaperPage } from "./pages/Whitepaper.js";
import { NotFoundPage } from "./pages/NotFound.js";
import { ApiDocsPage } from "./pages/ApiDocs.js";

const mapsApi = createMapsApiClient();

const pageRegistry = {
  "maps-home": MapsHomePage,
  "signals-list": NavigationSignalsPage,
  "signal-detail": SignalDetailPage,
  routes: RoutePredictionsPage,
  hazards: HazardsPage,
  congestion: CongestionPage,
  calibration: CalibrationPage,
  recommendations: RecommendationsPage,
  "story-types": StoryTypesPage,
  whitepaper: WhitepaperPage,
  docs: DocsPage,
  "api-docs": ApiDocsPage,
  "not-found": NotFoundPage,
};

function pageCount(response, key) {
  const items = response?.[key];
  if (!Array.isArray(items)) return null;
  const p = response?.pagination;
  if (!p) return items.length;
  return p.has_more ? "500+" : p.count;
}

export function App() {
  const [routeState, setRouteState] = useState(() => matchRoute(window.location.pathname));
  const [counts, setCounts] = useState({});

  useEffect(() => {
    function handlePopState() {
      setRouteState(matchRoute(window.location.pathname));
    }
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    Promise.all([
      mapsApi.listSignals({ limit: 500 }),
      mapsApi.listRoutes({ limit: 500 }),
      mapsApi.listHazards({ limit: 500 }),
      mapsApi.listSignals({ signalType: "congestion_formation", limit: 500 }),
    ]).then(([signals, routes, hazards, congestion]) => {
      setCounts({
        "/signals": pageCount(signals, "signals"),
        "/routes": pageCount(routes, "routes"),
        "/hazards": pageCount(hazards, "hazards"),
        "/congestion": pageCount(congestion, "signals"),
      });
    }).catch(() => {});
  }, []);

  function navigate(pathname) {
    if (pathname === routeState.pathname) return;
    window.history.pushState({}, "", pathname);
    setRouteState(matchRoute(pathname));
  }

  const PageComponent = pageRegistry[routeState.routeId] || NotFoundPage;

  return html`
    <${Layout} currentPath=${routeState.pathname} navigate=${navigate} counts=${counts}>
      <${PageComponent} api=${mapsApi} navigate=${navigate} params=${routeState.params} />
    <//>
  `;
}
