export const navigationItems = [
  { href: "/recommendations", label: "Recommendations" },
  { href: "/", label: "Traffic State" },
  { href: "/signals", label: "Signals" },
  { href: "/routes", label: "Routes" },
  { href: "/hazards", label: "Hazards" },
  { href: "/congestion", label: "Congestion" },
  { href: "/calibration", label: "Track Record" },
];

export const headerLinks = [
  { href: "/whitepaper", label: "Whitepaper" },
  { href: "/docs", label: "Docs" },
  { href: "/api-docs", label: "API" },
];

const routeDefinitions = [
  { id: "maps-home", path: "/" },
  { id: "maps-home", path: "/maps" },
  { id: "recommendations", path: "/recommendations" },
  { id: "signals-list", path: "/signals" },
  { id: "signal-detail", path: "/signals/:id" },
  { id: "routes", path: "/routes" },
  { id: "hazards", path: "/hazards" },
  { id: "congestion", path: "/congestion" },
  { id: "calibration", path: "/calibration" },
  { id: "story-types", path: "/story-types" },
  { id: "whitepaper", path: "/whitepaper" },
  { id: "docs", path: "/docs" },
  { id: "api-docs", path: "/api-docs" },
];

export function matchRoute(pathname) {
  const normalizedPath = normalizePathname(pathname);
  for (const definition of routeDefinitions) {
    const match = matchPath(definition.path, normalizedPath);
    if (match) {
      return {
        routeId: definition.id,
        params: match.params,
        pathname: normalizedPath,
      };
    }
  }

  return {
    routeId: "not-found",
    params: {},
    pathname: normalizedPath,
  };
}

export function normalizePathname(pathname) {
  if (!pathname) {
    return "/";
  }
  const trimmed = pathname.endsWith("/") && pathname !== "/" ? pathname.slice(0, -1) : pathname;
  return trimmed || "/";
}

export function shouldHandleNavigation(event, href) {
  return !event.defaultPrevented &&
    event.button === 0 &&
    !event.metaKey &&
    !event.ctrlKey &&
    !event.shiftKey &&
    !event.altKey &&
    href.startsWith("/");
}

function matchPath(routePath, pathname) {
  const routeSegments = normalizePathname(routePath).split("/").filter(Boolean);
  const pathSegments = pathname.split("/").filter(Boolean);

  if (routeSegments.length !== pathSegments.length) {
    return null;
  }

  const params = {};
  for (let index = 0; index < routeSegments.length; index += 1) {
    const routeSegment = routeSegments[index];
    const pathSegment = pathSegments[index];
    if (routeSegment.startsWith(":")) {
      params[routeSegment.slice(1)] = decodeURIComponent(pathSegment);
      continue;
    }
    if (routeSegment !== pathSegment) {
      return null;
    }
  }

  return { params };
}
