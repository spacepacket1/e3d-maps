import { React, useEffect, useState } from "../vendor.js";

const el = React.createElement;

function StoryType({ st }) {
  return el("article", { className: "panel docs-story-type" },
    el("div", { className: "docs-story-header" },
      el("span", { className: "docs-category" }, st.category),
      el("h3", null, st.display_name)
    ),
    el("p", { className: "docs-section-label" }, "What it means"),
    el("p", null, st.human_meaning),
    el("p", { className: "docs-section-label" }, "How agents use it"),
    el("p", null, st.agent_meaning),
    st.inputs && st.inputs.length ? el(React.Fragment, null,
      el("p", { className: "docs-section-label" }, "Inputs"),
      el("p", { className: "docs-tags" },
        ...st.inputs.map((i) => el("span", { key: i, className: "docs-tag" }, i))
      )
    ) : null,
    st.outputs && st.outputs.length ? el(React.Fragment, null,
      el("p", { className: "docs-section-label" }, "Outputs"),
      el("p", { className: "docs-tags" },
        ...st.outputs.map((o) => el("span", { key: o, className: "docs-tag" }, o))
      )
    ) : null,
    st.example_questions && st.example_questions.length ? el(React.Fragment, null,
      el("p", { className: "docs-section-label" }, "Example questions"),
      el("ul", { className: "docs-questions" },
        ...st.example_questions.map((q) => el("li", { key: q }, q))
      )
    ) : null,
    st.related_navigation_signal_types && st.related_navigation_signal_types.length ? el(React.Fragment, null,
      el("p", { className: "docs-section-label" }, "Related signal types"),
      el("p", { className: "docs-tags" },
        ...st.related_navigation_signal_types.map((s) => el("span", { key: s, className: "docs-tag docs-tag-signal" }, s))
      )
    ) : null
  );
}

export function DocsPage({ api }) {
  const [state, setState] = useState({ loading: true, error: "", storyTypes: [] });

  useEffect(() => {
    let cancelled = false;
    api.listStoryTypes({ limit: 100 }).then((response) => {
      if (cancelled) return;
      setState({
        loading: false,
        error: "",
        storyTypes: Array.isArray(response?.story_types) ? response.story_types : [],
      });
    }).catch((error) => {
      if (cancelled) return;
      setState({ loading: false, error: error instanceof Error ? error.message : String(error), storyTypes: [] });
    });
    return () => { cancelled = true; };
  }, [api]);

  return el("div", null,
    el("section", { className: "page-header" },
      el("div", null,
        el("p", { className: "eyebrow" }, "Docs"),
        el("h2", null, "Story Types")
      )
    ),
    el("div", { className: "panel docs-intro" },
      el("p", null,
        "Think of E3D Maps as Google Maps for on-chain capital: where is money moving, what routes are congested, where are the hazards, and which destinations are gaining probability? Instead of routing cars around traffic, E3D Maps routes trading agents, treasury agents, and research agents around liquidity events, whale movements, and exchange flow shifts — in real time."
      ),
      el("p", { style: { marginTop: "12px" } },
        "Story types are the input taxonomy for Maps agents. When the E3D platform publishes a story, its type tells the agents what kind of navigation evidence it contains — and which signal types it can support. Agents read stories from ",
        el("code", null, "e3d.ai"),
        ", classify them by type, and use them as evidence when writing NavigationSignals to ClickHouse."
      )
    ),
    state.error ? el("p", { className: "error-banner" }, state.error) : null,
    state.loading
      ? el("p", { className: "empty-copy" }, "Loading...")
      : !state.storyTypes.length
        ? el("p", { className: "empty-copy" }, "No story types are defined yet.")
        : el(React.Fragment, null,
            ...state.storyTypes.map((st) => el(StoryType, { key: st.story_type, st }))
          )
  );
}
