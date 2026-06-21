import { html, useEffect, useState } from "../vendor.js";
import { titleCaseLabel, toArray } from "../formatters.js";

const AUTO_REFRESH_MS = 60_000;
const NEWS_STALE_MINUTES = 15;

function formatRelativeUpdatedAt(value) {
  if (!value) {
    return { label: "Update time unavailable", isStale: true };
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return { label: `Updated ${value}`, isStale: true };
  }

  const deltaMs = Math.max(0, Date.now() - date.getTime());
  const deltaMinutes = Math.round(deltaMs / 60_000);
  const deltaHours = Math.round(deltaMs / 3_600_000);
  const deltaDays = Math.round(deltaMs / 86_400_000);

  let label = "Updated just now";
  if (deltaMinutes >= 1 && deltaMinutes < 60) {
    label = `Updated ${deltaMinutes} minute${deltaMinutes === 1 ? "" : "s"} ago`;
  } else if (deltaMinutes >= 60 && deltaHours < 24) {
    label = `Updated ${deltaHours} hour${deltaHours === 1 ? "" : "s"} ago`;
  } else if (deltaHours >= 24) {
    label = `Updated ${deltaDays} day${deltaDays === 1 ? "" : "s"} ago`;
  }

  return { label, isStale: deltaMs > NEWS_STALE_MINUTES * 60_000 };
}

function stanceClass(stance) {
  switch (stance) {
    case "risk_on":
      return "maps-news-hero stance-risk-on";
    case "risk_off":
      return "maps-news-hero stance-risk-off";
    case "crowded":
      return "maps-news-hero stance-crowded";
    case "cautious":
      return "maps-news-hero stance-cautious";
    default:
      return "maps-news-hero stance-neutral";
  }
}

function normalizeNewsBriefs(response) {
  if (Array.isArray(response?.news_briefs)) return response.news_briefs;
  return response?.news ? [response.news] : [];
}

export function NewsPage({ api }) {
  const [state, setState] = useState({
    loading: true,
    refreshing: false,
    error: "",
    newsBriefs: [],
  });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function loadNews(isRefresh) {
      setState((current) => ({
        ...current,
        loading: current.loading && !isRefresh,
        refreshing: isRefresh,
        error: "",
      }));

      try {
        const response = await api.listNews({ limit: 5 });
        if (cancelled) return;
        setState({
          loading: false,
          refreshing: false,
          error: "",
          newsBriefs: normalizeNewsBriefs(response),
        });
      } catch (error) {
        if (cancelled) return;
        setState({
          loading: false,
          refreshing: false,
          error: error instanceof Error ? error.message : String(error),
          newsBriefs: [],
        });
      }
    }

    loadNews(reloadToken > 0);
    const timer = window.setInterval(() => loadNews(true), AUTO_REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [api, reloadToken]);

  const [latestNews, ...previousBriefs] = state.newsBriefs;
  const mapsNews = latestNews || null;
  const newsTimestamp = formatRelativeUpdatedAt(mapsNews?.generated_at);

  return html`
    <section className="page-header">
      <div>
        <p className="eyebrow">Maps News</p>
        <h2>Latest market briefs</h2>
      </div>
      <button className="action-button" type="button" onClick=${() => setReloadToken((value) => value + 1)}>
        ${state.refreshing ? "Refreshing..." : "Refresh"}
      </button>
    </section>

    ${state.error ? html`<p className="error-banner">${state.error}</p>` : null}
    ${state.loading
      ? html`<p className="empty-copy">Loading Maps News...</p>`
      : html`
          <section className=${stanceClass(mapsNews?.stance)}>
            <div className="maps-news-copy">
              <p className="eyebrow">Latest Brief</p>
              ${mapsNews
                ? html`
                    <h3>${mapsNews.headline}</h3>
                    <p className="maps-news-summary">${mapsNews.summary}</p>
                    <div className="maps-news-meta">
                      <span className=${newsTimestamp.isStale ? "maps-news-timestamp is-stale" : "maps-news-timestamp"}>
                        ${newsTimestamp.label}
                      </span>
                      <span className="maps-news-meta-sep">•</span>
                      <span className="maps-news-meta-value">${titleCaseLabel(mapsNews.stance)}</span>
                    </div>
                    <div className="maps-news-tags">
                      ${toArray(mapsNews.tags).map(
                        (tag) => html`<span key=${tag} className="badge badge-neutral">${titleCaseLabel(tag)}</span>`
                      )}
                    </div>
                  `
                : html`
                    <h3>Maps News is warming up.</h3>
                    <p className="maps-news-summary">
                      The bulletin will appear here once the latest market brief has been published.
                    </p>
                  `}
            </div>
          </section>
          ${previousBriefs.length
            ? html`
                <section className="news-brief-list" aria-label="Previous Maps News briefs">
                  ${previousBriefs.map((brief) => {
                    const timestamp = formatRelativeUpdatedAt(brief.generated_at);
                    return html`
                      <article key=${`${brief.generated_at}-${brief.headline}`} className="news-brief-card">
                        <div className="news-brief-card-header">
                          <span className="badge badge-neutral">${titleCaseLabel(brief.stance)}</span>
                          <span className=${timestamp.isStale ? "maps-news-timestamp is-stale" : "maps-news-timestamp"}>
                            ${timestamp.label}
                          </span>
                        </div>
                        <h3>${brief.headline}</h3>
                        <p>${brief.summary}</p>
                        <div className="maps-news-tags">
                          ${toArray(brief.tags).map(
                            (tag) => html`<span key=${`${brief.generated_at}-${tag}`} className="badge badge-neutral">${titleCaseLabel(tag)}</span>`
                          )}
                        </div>
                      </article>
                    `;
                  })}
                </section>
              `
            : null}
        `}
  `;
}
