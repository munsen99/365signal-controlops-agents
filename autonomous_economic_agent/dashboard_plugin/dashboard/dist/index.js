(function () {
  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !SDK.React) {
    return;
  }
  const React = SDK.React;
  const { useEffect, useRef, useState } = SDK.hooks;
  const { Card, CardHeader, CardTitle, CardContent, Badge } = SDK.components;
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

  function ynClass(value) {
    if (value === "yes" || value === "present" || value === "healthy" || value === "mismatch") {
      return value === "healthy" ? "ok" : "warn";
    }
    if (value === "no" || value === "absent") {
      return "ok";
    }
    return "warn";
  }

  function Pill(props) {
    const value = safeText(props.value || "unknown", 32);
    const cls = ynClass(props.value) === "ok" && props.warnOnYes !== true ? "ok" : "warn";
    const forceWarn = props.forceWarn || value === "unknown" || value === "unavailable" || value === "mismatch" || value === "degraded" || value === "frozen" || value === "offline";
    return h("span", { className: "aea-pill " + (forceWarn ? "warn" : cls) }, value);
  }

  function Kpi(props) {
    return h("div", { className: "aea-kpi" },
      h("div", { className: "label" }, props.label),
      h("div", { className: "value" }, safeText(props.value == null ? "unavailable" : props.value, 48)),
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
    const warn = rail.health && rail.health !== "healthy";
    const nativeLabel = rail.native_asset === "ETH" ? "ETH gas reserve" : "SOL fee reserve";
    return h(Section, {
      title: rail.rail === "evm" ? "EVM rail" : "Solana rail",
      className: warn ? "aea-state-degraded" : "",
    },
      h(Row, { label: "Health" }, h(Pill, { value: rail.health || "unknown", forceWarn: warn })),
      h(Row, { label: "Network", value: rail.network }),
      rail.rail === "evm" ? h(Row, { label: "Chain ID", value: rail.chain_id }) : null,
      h(Row, { label: "Public wallet", value: rail.public_wallet }),
      h(Row, { label: "USDC balance", value: rail.usdc_balance }),
      h(Row, { label: nativeLabel, value: rail.native_reserve }),
      rail.rail === "evm" ? h(Row, { label: "Canonical token", value: rail.canonical_token }) : null,
      h(Row, { label: "Reconciliation" }, h(Pill, { value: rail.reconciliation || "unavailable", forceWarn: rail.reconciliation !== "healthy" })),
      h(Row, { label: rail.rail === "evm" ? "Last tx hash" : "Last signature", value: rail.last_settlement_ref }),
      h(Row, { label: "Last settlement", value: rail.last_settlement_status }),
      rail.detail ? h("div", { className: "aea-meta" }, safeText(rail.detail, 160)) : null,
    );
  }

  function emptyStatus() {
    return {
      ok: false,
      agent: { state: "offline", health: "unavailable", runtime_health: "unavailable" },
      economics: { source: "unavailable" },
      supervisor: { readable: "unknown", frozen: "unknown", signer_enabled: "unknown", loop_enabled: "unknown", live_spend_gate: "unknown" },
      policy: { verified: "unknown" },
      reconciliation: { health: "unavailable", rows: [], mismatches: [] },
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
        const fetchJSON = SDK.fetchJSON;
        const pending = fetchJSON("/api/plugins/aea/status");
        Promise.resolve(pending)
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
        if (visible.current) {
          load();
        }
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
    const agent = status.agent || {};
    const econ = status.economics || {};
    const sup = status.supervisor || {};
    const policy = status.policy || {};
    const recon = status.reconciliation || {};
    const job = status.current_job || { present: false };
    const rails = Array.isArray(status.rails) ? status.rails : [];
    const events = Array.isArray(status.recent_events) ? status.recent_events.slice(0, 20) : [];
    const warnings = Array.isArray(status.warnings) ? status.warnings : [];
    const state = agent.state || "offline";
    const bannerClass = "aea-banner aea-state-" + (
      state === "frozen" ? "frozen" :
      recon.health === "mismatch" ? "mismatch" :
      agent.health === "unknown" || sup.readable === "unknown" ? "unknown" :
      state === "offline" ? "offline" :
      agent.health === "degraded" ? "degraded" : ""
    );

    const sol = rails.find(function (r) { return r.rail === "solana"; });
    const evm = rails.find(function (r) { return r.rail === "evm"; });

    return h("div", { className: "aea-dash" },
      h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "1rem" } },
        h("h1", null, "Autonomous Economic Agent"),
        h("div", { className: "aea-meta" },
          "Last successful refresh: ",
          lastOk ? lastOk : "never",
          stale ? " (stale)" : "",
        ),
      ),
      warnings.length || error ? h("div", { className: bannerClass || "aea-banner aea-state-degraded" },
        safeText(error || warnings.join(" · "), 400),
      ) : null,
      h("div", { className: "aea-kpis" },
        h(Kpi, { label: "Agent state", value: state }),
        h(Kpi, { label: "Available USDC", value: econ.available_capital_usdc }),
        h(Kpi, { label: "Verified revenue", value: econ.verified_revenue_usdc }),
        h(Kpi, { label: "P&L", value: econ.realized_pnl_usdc }),
        h(Kpi, { label: "Capital at risk", value: econ.capital_at_risk_usdc }),
      ),
      h("div", { className: "aea-grid" },
        h(Section, { title: "Safety & supervisor", className: (sup.frozen === "yes" || sup.readable !== "yes") ? "aea-state-degraded" : "" },
          h(Row, { label: "Frozen" }, h(Pill, { value: sup.frozen, forceWarn: sup.frozen !== "no" })),
          h(Row, { label: "Signer enabled" }, h(Pill, { value: sup.signer_enabled, forceWarn: sup.signer_enabled !== "yes" && sup.signer_enabled !== "no" })),
          h(Row, { label: "Loop enabled" }, h(Pill, { value: sup.loop_enabled })),
          h(Row, { label: "Live spend gate" }, h(Pill, { value: sup.live_spend_gate, forceWarn: sup.live_spend_gate !== "absent" })),
          h(Row, { label: "Supervisor readable" }, h(Pill, { value: sup.readable, forceWarn: sup.readable !== "yes" })),
          h(Row, { label: "Policy version", value: policy.version }),
          h(Row, { label: "Policy hash", value: policy.hash }),
          h(Row, { label: "Policy verified" }, h(Pill, { value: policy.verified, forceWarn: policy.verified !== "yes" })),
        ),
        h(Section, { title: "Reconciliation", className: recon.health !== "healthy" ? "aea-state-mismatch" : "" },
          h(Row, { label: "Health" }, h(Pill, { value: recon.health || "unavailable", forceWarn: recon.health !== "healthy" })),
          h(Row, { label: "Mismatches", value: Array.isArray(recon.mismatches) ? String(recon.mismatches.length) : "unavailable" }),
          h(Row, { label: "Opening capital USDC", value: econ.opening_capital_usdc }),
          h(Row, { label: "Verified revenue USDC", value: econ.verified_revenue_usdc }),
          h(Row, { label: "Attributable costs", value: econ.attributable_costs_usdc }),
          h(Row, { label: "SOL fee reserve", value: econ.fee_reserve_sol }),
          h(Row, { label: "ETH gas reserve", value: econ.fee_reserve_eth }),
          h("div", { className: "aea-meta" }, "Opening capital is capital, never revenue."),
        ),
        h(Section, { title: "Active / last job" },
          job.present ? [
            h(Row, { key: "id", label: "Job ID", value: job.job_id }),
            h(Row, { key: "title", label: "Title", value: safeText(job.title, 120) }),
            h(Row, { key: "mkt", label: "Marketplace", value: safeText(job.marketplace, 64) }),
            h(Row, { key: "st", label: "Status", value: safeText(job.status, 32) }),
            h(Row, { key: "rew", label: "Expected reward", value: job.expected_reward_usdc }),
            h(Row, { key: "cost", label: "Expected cost", value: job.expected_cost_usdc }),
            h(Row, { key: "mgn", label: "Expected margin", value: job.expected_margin_usdc }),
            h(Row, { key: "acc", label: "Accepted", value: job.accepted_at }),
            h(Row, { key: "sub", label: "Submitted", value: job.submitted_at }),
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
              h("th", null, "Event"),
              h("th", null, "Identifier"),
              h("th", null, "Status"),
            )),
            h("tbody", null, events.map(function (ev, idx) {
              return h("tr", { key: String(idx) + (ev.timestamp || "") },
                h("td", null, safeText(ev.timestamp, 40)),
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
