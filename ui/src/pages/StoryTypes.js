import { html, useEffect, useState } from "../vendor.js";
import { titleCaseLabel } from "../formatters.js";

export function StoryTypesPage({ api }) {
  const [state, setState] = useState({
    loading: true,
    error: "",
    storyTypes: [],
  });

  useEffect(() => {
    let cancelled = false;

    async function loadStoryTypes() {
      try {
        const response = await api.listStoryTypes({ limit: 100 });
        if (cancelled) {
          return;
        }
        setState({
          loading: false,
          error: "",
          storyTypes: Array.isArray(response?.story_types) ? response.story_types : [],
        });
      } catch (error) {
        if (cancelled) {
          return;
        }
        setState({
          loading: false,
          error: error instanceof Error ? error.message : String(error),
          storyTypes: [],
        });
      }
    }

    loadStoryTypes();
    return () => {
      cancelled = true;
    };
  }, [api]);

  return html`
    <section className="page-header">
      <div>
        <p className="eyebrow">Story Types</p>
        <h2>Story taxonomy</h2>
      </div>
    </section>
    ${state.error ? html`<p className="error-banner">${state.error}</p>` : null}
    ${state.loading
      ? html`<p className="empty-copy">Loading story type definitions...</p>`
      : !state.storyTypes.length
        ? html`<p className="empty-copy">No story types are available.</p>`
        : html`
            <section className="story-grid">
              ${state.storyTypes.map(
                (storyType) => html`
                  <article key=${storyType.story_type} className="panel">
                    <p className="panel-label">${titleCaseLabel(storyType.category)}</p>
                    <h3>${storyType.display_name}</h3>
                    <p>${storyType.human_meaning}</p>
                    <p><strong>Agent meaning:</strong> ${storyType.agent_meaning}</p>
                    <p>
                      <strong>Related signals:</strong>
                      ${(storyType.related_navigation_signal_types || []).join(", ") || "n/a"}
                    </p>
                  </article>
                `
              )}
            </section>
          `}
  `;
}
