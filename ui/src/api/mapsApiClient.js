function buildUrl(baseUrl, pathname, query) {
  const entries = Object.entries(query || {}).filter(([, value]) => value !== undefined && value !== null && value !== "");
  if (!baseUrl) {
    const search = new URLSearchParams(entries.map(([key, value]) => [key, String(value)]));
    const suffix = search.toString();
    return suffix ? `${pathname}?${suffix}` : pathname;
  }

  const url = new URL(pathname, baseUrl);
  for (const [key, value] of entries) {
    url.searchParams.set(key, String(value));
  }
  return url.toString();
}

function emptyPage(key) {
  return {
    [key]: [],
    pagination: {
      count: 0,
      has_more: false,
      limit: 0,
      offset: 0,
    },
  };
}

export function createMapsApiClient({ baseUrl = "", fetchImpl = globalThis.fetch } = {}) {
  if (typeof fetchImpl !== "function") {
    throw new Error("A fetch implementation is required.");
  }

  async function request(pathname, { allowNotFound = false, query } = {}) {
    const response = await fetchImpl(buildUrl(baseUrl, pathname, query), {
      headers: {
        Accept: "application/json",
      },
    });

    if (response.status === 404 && allowNotFound) {
      return null;
    }

    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = await response.json();
        detail = body?.error || body?.detail || detail;
      } catch {
        // Keep the status text fallback.
      }
      throw new Error(`Maps API request failed (${response.status}): ${detail}`);
    }

    return response.json();
  }

  return {
    async getState() {
      const body = await request("/api/maps/state", { allowNotFound: true });
      return body?.state || null;
    },
    async getNews() {
      const body = await request("/api/maps/news", { allowNotFound: true });
      return body?.news || null;
    },
    async getCrossChainActivity() {
      const body = await request("/api/maps/cross-chain", { allowNotFound: true });
      return body?.cross_chain || null;
    },
    async listSignals(filters = {}) {
      const body = await request("/api/maps/signals", {
        query: {
          signal_type: filters.signalType,
          asset: filters.asset,
          chain: filters.chain,
          time_horizon_hours: filters.timeHorizonHours,
          min_confidence: filters.minConfidence,
          limit: filters.limit,
          offset: filters.offset,
        },
      });
      return body || emptyPage("signals");
    },
    async getSignal(id) {
      const body = await request(`/api/maps/signals/${encodeURIComponent(id)}`, { allowNotFound: true });
      return body?.signal || null;
    },
    async listRoutes(filters = {}) {
      const body = await request("/api/maps/routes", {
        query: {
          limit: filters.limit,
          offset: filters.offset,
        },
      });
      return body || emptyPage("routes");
    },
    async listHazards(filters = {}) {
      const body = await request("/api/maps/hazards", {
        query: {
          limit: filters.limit,
          offset: filters.offset,
        },
      });
      return body || emptyPage("hazards");
    },
    async getFlowGraph() {
      const body = await request("/api/maps/graph", { allowNotFound: true });
      return body || null;
    },
    async getCalibration(filters = {}) {
      const body = await request("/api/maps/calibration", {
        allowNotFound: true,
        query: { lookback_days: filters.lookbackDays },
      });
      return body?.calibration || null;
    },
    async listStoryTypes(filters = {}) {
      const body = await request("/api/story-types", {
        query: {
          limit: filters.limit,
          offset: filters.offset,
        },
      });
      return body || emptyPage("story_types");
    },
    async getRecommendations(filters = {}) {
      const body = await request("/api/maps/recommendations", {
        query: {
          objective: filters.objective,
          asset: filters.asset,
          address: filters.address,
          storyType: filters.storyType,
          maxResults: filters.maxResults,
        },
      });
      return body || { generatedAt: null, objective: null, recommendations: [] };
    },
  };
}

export { buildUrl, emptyPage };
