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
import { StoryTypesPage } from "./pages/StoryTypes.js";
import { NotFoundPage } from "./pages/NotFound.js";

const mapsApi = createMapsApiClient();

const pageRegistry = {
  "maps-home": MapsHomePage,
  "signals-list": NavigationSignalsPage,
  "signal-detail": SignalDetailPage,
  routes: RoutePredictionsPage,
  hazards: HazardsPage,
  congestion: CongestionPage,
  "story-types": StoryTypesPage,
  "not-found": NotFoundPage,
};

export function App() {
  const [routeState, setRouteState] = useState(() => matchRoute(window.location.pathname));

  useEffect(() => {
    function handlePopState() {
      setRouteState(matchRoute(window.location.pathname));
    }

    window.addEventListener("popstate", handlePopState);
    return () => {
      window.removeEventListener("popstate", handlePopState);
    };
  }, []);

  function navigate(pathname) {
    if (pathname === routeState.pathname) {
      return;
    }
    window.history.pushState({}, "", pathname);
    setRouteState(matchRoute(pathname));
  }

  const PageComponent = pageRegistry[routeState.routeId] || NotFoundPage;

  return html`
    <${Layout} currentPath=${routeState.pathname} navigate=${navigate}>
      <${PageComponent} api=${mapsApi} navigate=${navigate} params=${routeState.params} />
    <//>
  `;
}
