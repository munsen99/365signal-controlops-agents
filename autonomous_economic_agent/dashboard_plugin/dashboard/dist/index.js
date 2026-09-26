(function () {
  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !SDK.React) {
    return;
  }
  const React = SDK.React;
  const { useEffect, useRef, useState } = SDK.hooks;
  const { Card, CardHeader, CardTitle, CardContent } = SDK.components;
  const h = React.createElement;
  const REFRESH_MS = 8000;
  const TAG_RE = /<[^>]*>/g;
  const CONTROL_RE = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g;

  function safeText(value, maxLen) {
    const limit = typeof maxLen === "number" ? maxLen : 240;
    let text = value == null ? "" : String(value);
    text = text.replace(CONTROL_RE, "").replace(TAG_RE, "");
    if (text.length > limit) {
      text = text.slice(0, limit - 1) + "…";
    }
    return text;
  }

  function freshnessOf(value, freshness) {
    const v = safeText(value == null || value === "" ? "—" : value, 64);
    const f = safeText(freshness || "unknown", 16);
    return v + " · " + f;
  }

  function Pill(props) {
    const value = safeText(props.value || "unknown", 40);
    const forceWarn = props.forceWarn || [
      "unknown", "unavailable", "mismatch", "degraded", "frozen", "offline", "stale",
    ].indexOf(value.split(" ")[0]) >= 0 || value.indexOf("stale") >= 0 || value.indexOf("unknown") >= 0;
    return h("span", { className: "aea-pill " + (forceWarn ? "warn" : "ok") }, value);
  }

  function Kpi(props) {
    return h("div", { className: "aea-kpi" },
      h("div", { className: "label" }, props.label),
      h("div", { className: "value" }, safeText(props.value == null ? "—" : props.value, 48)),
      props.hint ? h("div", { className: "hint" }, safeText(props.hint, 80)) : null,
    );
  }

  function Row(props) {
    return h("div", { className: "aea-row" },
      h("span", null, props.label),
      h("span", null, props.children || safeText(props.value == null ? "—" : props.value, 96)),
    );
  }

  function Section(props) {
    return h(Card, { className: "aea-card " + (props.className || "") },
      h(CardHeader, null, h(CardTitle, null, props.title)),
      h(CardContent, null, props.children),
    );
  }

  function RailCard(props) {
    const rail = props.rail || {};
    const warn = rail.health !== "healthy" || rail.wallet_read !== "current" || rail.reconciliation !== "healthy";
    const nativeLabel = rail.native_asset === "ETH" ? "ETH gas reserve" : "SOL fee reserve";
    return h(Section, {
      title: (rail.rail === "evm" ? "EVM rail" : "Solana rail") + (rail.context_id ? " · " + rail.context_id : ""),
      className: warn ? "aea-state-degraded" : "",
    },
      h(Row, { label: "Configured network", value: rail.configured_network || rail.network }),
      rail.rail === "evm" ? h(Row, { label: "Chain ID", value: rail.chain_id }) : null,
      h(Row, { label: "Configured public wallet", value: rail.configured_public_wallet || rail.public_wallet }),
      h(Row, { label: "Wallet read" }, h(Pill, { value: rail.wallet_read || "unknown", forceWarn: rail.wallet_read !== "current" })),
      h(Row, { label: "Current USDC", value: rail.current_usdc_balance }),
      h(Row, { label: "Current " + nativeLabel, value: rail.current_native_reserve }),
      h(Row, { label: "Last-known USDC", value: freshnessOf(rail.last_known_usdc_balance, rail.wallet_read === "current" ? "current" : "stale") }),
      h(Row, { label: "Last-known " + nativeLabel, value: rail.last_known_native_reserve }),
      h(Row, { label: "Last-known as of", value: rail.last_known_as_of }),
      h(Row, { label: "Last-known source", value: rail.last_known_source }),
      rail.rail === "evm" ? h(Row, { label: "Canonical token", value: rail.canonical_token }) : h(Row, { label: "Canonical mint", value: rail.canonical_token }),
      h(Row, { label: "Reconciliation" }, h(Pill, {
        value: (rail.reconciliation || "unknown") + " · " + (rail.reconciliation_freshness || "unknown"),
        forceWarn: rail.reconciliation !== "healthy",
      })),
      h(Row, { label: rail.rail === "evm" ? "Last tx hash" : "Last signature", value: rail.last_settlement_ref }),
      h(Row, { label: "Last settlement", value: freshnessOf(rail.last_settlement_status, rail.last_settlement_freshness) }),
      rail.detail ? h("div", { className: "aea-meta" }, safeText(rail.detail, 200)) : null,
    );
  }

  function emptyStatus() {
    return {
      ok: false,
      observation: { degraded: true, banner: "OBSERVATION DEGRADED — observability API unavailable.", reasons: [] },
      agent: { state: "offline", health: "unavailable", runtime_health: "unavailable" },
      economics: { source: "unavailable", available_capital_usdc: null, available_capital_freshness: "unknown", available_capital_label: "no current wallet read" },
      supervisor: { readable: "unknown", frozen: "unknown", frozen_freshness: "unknown", signer_enabled: "unknown", signer_enabled_freshness: "unknown", loop_enabled: "unknown", loop_enabled_freshness: "unknown", live_spend_gate: "unknown" },
      policy: { verified: "unknown" },
      reconciliation: { health: "unknown", freshness: "unknown", rows: [], mismatches: [] },
      contexts: [],
      rails: [],
      current_job: { present: false, untrusted: true },
      recent_events: [],
      warnings: ["AEA observability API unavailable"],
    };
  }

  function AeaDashboard() {
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    const [lastOk, setLastOk] = useState(null);
    const [stale, setStale] = useState(false);
    const visible = useRef(typeof document === "undefined" || document.visibilityState !== "hidden");

    useEffect(function () {
      let cancelled = false;
      let timer = null;

      function load() {
        if (cancelled || !visible.current) {
          return;
        }
        Promise.resolve(SDK.fetchJSON("/api/plugins/aea/status"))
          .then(function (body) {
            if (cancelled) return;
            setData(body && typeof body === "object" ? body : emptyStatus());
            setError(null);
            setStale(false);
            setLastOk(new Date().toISOString());
          })
          .catch(function () {
            if (cancelled) return;
            setError("AEA observability request failed");
            setStale(true);
            setData(function (prev) { return prev || emptyStatus(); });
          });
      }

      function onVis() {
        visible.current = document.visibilityState !== "hidden";
        if (visible.current) load();
      }

      load();
      timer = setInterval(load, REFRESH_MS);
      document.addEventListener("visibilitychange", onVis);
      return function () {
        cancelled = true;
        if (timer) clearInterval(timer);
        document.removeEventListener("visibilitychange", onVis);
      };
    }, []);

    const status = data || emptyStatus();
    const obs = status.observation || {};
    const agent = status.agent || {};
    const econ = status.economics || {};
    const sup = status.supervisor || {};
    const policy = status.policy || {};
    const recon = status.reconciliation || {};
    const job = status.current_job || { present: false };
    const rails = Array.isArray(status.rails) ? status.rails : [];
    const contexts = Array.isArray(status.contexts) ? status.contexts : [];
    const events = Array.isArray(status.recent_events) ? status.recent_events.slice(0, 20) : [];
    const state = agent.state || "offline";
    const sol = rails.find(function (r) { return r.rail === "solana"; });
    const evm = rails.find(function (r) { return r.rail === "evm"; });
    const banner = obs.banner || error;

    return h("div", { className: "aea-dash" },
      h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "1rem" } },
        h("h1", null, "Autonomous Economic Agent"),
        h("div", { className: "aea-meta" },
          "Last successful refresh: ",
          lastOk ? lastOk : "never",
          stale ? " (stale)" : "",
        ),
      ),
      banner ? h("div", { className: "aea-banner" }, safeText(banner, 400)) : null,
      h("div", { className: "aea-kpis" },
        h(Kpi, { label: "Agent state", value: state }),
        h(Kpi, {
          label: "Available USDC",
          value: econ.available_capital_usdc == null ? "—" : econ.available_capital_usdc,
          hint: econ.available_capital_label || econ.available_capital_freshness,
        }),
        h(Kpi, { label: "M1 verified revenue", value: econ.verified_revenue_usdc, hint: "default context only" }),
        h(Kpi, { label: "M1 P&L", value: econ.realized_pnl_usdc, hint: "not summed across contexts" }),
        h(Kpi, { label: "M1 capital at risk", value: econ.capital_at_risk_usdc, hint: "default context only" }),
      ),
      h(Section, { title: "Economic contexts" },
        contexts.length === 0 ? h("div", { className: "aea-empty" }, "No economic contexts.") :
          h("div", { className: "aea-grid" }, contexts.map(function (ctx) {
            return h("div", { key: ctx.id, className: "aea-card" + (ctx.ledger_available ? "" : " aea-state-degraded") },
              h("h2", null, safeText(ctx.id, 40)),
              h(Row, { label: "Purpose", value: ctx.purpose }),
              h(Row, { label: "Rail / network", value: (ctx.rail || "") + " · " + (ctx.network || "—") }),
              h(Row, { label: "Database", value: ctx.database }),
              h(Row, { label: "Ledger" }, h(Pill, { value: ctx.ledger_available ? "available" : "unavailable", forceWarn: !ctx.ledger_available })),
              h(Row, { label: "Opening capital", value: ctx.opening_capital_usdc }),
              h(Row, { label: "Available USDC", value: freshnessOf(ctx.available_capital_usdc, ctx.available_capital_freshness) }),
              h(Row, { label: "Verified revenue", value: ctx.verified_revenue_usdc }),
              h(Row, { label: "Costs", value: ctx.attributable_costs_usdc }),
              h(Row, { label: "P&L", value: ctx.realized_pnl_usdc }),
              h(Row, { label: "Reconciliation" }, h(Pill, {
                value: (ctx.reconciliation || "unknown") + " · " + (ctx.reconciliation_freshness || "unknown"),
                forceWarn: ctx.reconciliation !== "healthy",
              })),
              h(Row, { label: "Last activity", value: ctx.last_activity_at }),
            );
          })),
      ),
      h("div", { className: "aea-grid" },
        h(Section, { title: "Safety & supervisor", className: (sup.readable !== "yes") ? "aea-state-degraded" : "" },
          h(Row, { label: "Supervisor readable" }, h(Pill, { value: sup.readable, forceWarn: sup.readable !== "yes" })),
          h(Row, { label: "Frozen" }, h(Pill, { value: freshnessOf(sup.frozen, sup.frozen_freshness), forceWarn: sup.frozen_freshness !== "current" })),
          h(Row, { label: "Signer enabled" }, h(Pill, { value: freshnessOf(sup.signer_enabled, sup.signer_enabled_freshness), forceWarn: sup.signer_enabled_freshness !== "current" })),
          h(Row, { label: "Loop enabled" }, h(Pill, { value: freshnessOf(sup.loop_enabled, sup.loop_enabled_freshness), forceWarn: sup.loop_enabled_freshness !== "current" })),
          h(Row, { label: "Live spend gate" }, h(Pill, { value: sup.live_spend_gate, forceWarn: sup.live_spend_gate !== "absent" })),
          h(Row, { label: "Policy version", value: policy.version }),
          h(Row, { label: "Policy hash", value: policy.hash }),
          h(Row, { label: "Policy verified" }, h(Pill, { value: policy.verified, forceWarn: policy.verified !== "yes" })),
          sup.detail ? h("div", { className: "aea-meta" }, safeText(sup.detail, 200)) : null,
        ),
        h(Section, { title: "Reconciliation", className: recon.health !== "healthy" ? "aea-state-mismatch" : "" },
          h(Row, { label: "Health" }, h(Pill, { value: (recon.health || "unknown") + " · " + (recon.freshness || "unknown"), forceWarn: recon.health !== "healthy" })),
          h(Row, { label: "Last success", value: recon.last_success_at }),
          h("div", { className: "aea-meta" }, safeText(recon.detail || "Current healthy requires a live wallet read with zero delta.", 200)),
        ),
        h(Section, { title: "Active / last job" },
          job.present ? [
            h(Row, { key: "ctx", label: "Context", value: job.context_id }),
            h(Row, { key: "id", label: "Job ID", value: job.job_id }),
            h(Row, { key: "title", label: "Title", value: safeText(job.title, 120) }),
            h(Row, { key: "mkt", label: "Marketplace", value: safeText(job.marketplace, 64) }),
            h(Row, { key: "st", label: "Status", value: safeText(job.status, 32) }),
            h(Row, { key: "rew", label: "Expected reward", value: job.expected_reward_usdc }),
            h(Row, { key: "cost", label: "Expected cost", value: job.expected_cost_usdc }),
            h(Row, { key: "mgn", label: "Expected margin", value: job.expected_margin_usdc }),
            h(Row, { key: "pay", label: "Payment", value: job.payment_state }),
          ] : h("div", { className: "aea-empty" }, "No current or last job."),
        ),
      ),
      h("div", { className: "aea-rails" },
        sol ? h(RailCard, { rail: sol }) : h(Section, { title: "Solana rail" }, h("div", { className: "aea-empty" }, "Solana rail not configured.")),
        evm ? h(RailCard, { rail: evm }) : h(Section, { title: "EVM rail" }, h("div", { className: "aea-empty" }, "EVM rail not configured.")),
      ),
      h(Section, { title: "Recent activity" },
        events.length === 0 ? h("div", { className: "aea-empty" }, "No recent ledger events.") :
          h("table", { className: "aea-events" },
            h("thead", null, h("tr", null,
              h("th", null, "Time"),
              h("th", null, "Context"),
              h("th", null, "Rail"),
              h("th", null, "Network"),
              h("th", null, "Event"),
              h("th", null, "Identifier"),
              h("th", null, "Status"),
            )),
            h("tbody", null, events.map(function (ev, idx) {
              return h("tr", { key: String(idx) + (ev.timestamp || "") },
                h("td", null, safeText(ev.timestamp, 40)),
                h("td", null, safeText(ev.context_id, 32)),
                h("td", null, safeText(ev.rail, 16)),
                h("td", null, safeText(ev.network, 24)),
                h("td", null, safeText(ev.display_type || ev.event_type, 48)),
                h("td", null, safeText(ev.identifier, 80)),
                h("td", null, safeText(ev.status, 32)),
              );
            })),
          ),
      ),
    );
  }

  window.__HERMES_PLUGINS__.register("aea", AeaDashboard);
})();
