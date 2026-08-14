/* Command center controller.
 *
 * Boots from REST snapshots, then keeps itself current from the event stream.
 * Every event carries a sequence number, so a dropped connection resumes from
 * the last one applied rather than losing the middle of a mission.
 */

(() => {
  const $ = (id) => document.getElementById(id);
  const MAX_FEED = 500;

  const state = {
    cursor: 0,
    link: 'connecting',
    simulateMode: false,
    fleet: null,
    agents: new Map(),
    runs: [],
    runsById: new Map(),
    stagesByRun: new Map(),
    metrics: null,
    selectedAgent: null,
    selectedRun: null,
    feed: [],
    feedFilter: 'all',
    follow: true,
  };

  let map;
  let source;
  let retryDelay = 1000;

  /* ── helpers ───────────────────────────────────────────────────────── */

  // When the commander is started with --token, the console carries it in its
  // own URL; every request and the event stream reuse it from there.
  const TOKEN = new URLSearchParams(location.search).get('token') || '';

  const withToken = (path) => {
    if (!TOKEN) return path;
    return path + (path.includes('?') ? '&' : '?') + `token=${encodeURIComponent(TOKEN)}`;
  };

  const api = async (path, options) => {
    const headers = { 'Content-Type': 'application/json' };
    if (TOKEN) headers.Authorization = `Bearer ${TOKEN}`;
    const response = await fetch(withToken(path), { headers, ...options });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || `request failed (${response.status})`);
    return body;
  };

  const clock = (ts) => new Date((ts || 0) * 1000).toLocaleTimeString([], {
    hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit',
  });

  const duration = (seconds) => {
    if (seconds === null || seconds === undefined) return '—';
    if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    const mins = Math.floor(seconds / 60);
    return `${mins}m ${String(Math.round(seconds % 60)).padStart(2, '0')}s`;
  };

  const ago = (ts) => {
    if (!ts) return '—';
    const delta = Date.now() / 1000 - ts;
    if (delta < 60) return `${Math.max(0, Math.round(delta))}s ago`;
    if (delta < 3600) return `${Math.round(delta / 60)}m ago`;
    if (delta < 86400) return `${Math.round(delta / 3600)}h ago`;
    return `${Math.round(delta / 86400)}d ago`;
  };

  const node = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };

  /* ── boot ──────────────────────────────────────────────────────────── */

  async function boot() {
    map = new window.FleetMap($('map'), $('map-shell'), {
      onSelect: (agentId) => {
        state.selectedAgent = agentId;
        renderRoster();
        if (agentId) openDrawer(agentId); else closeDrawer();
      },
    });

    bindControls();

    try {
      const health = await api('/api/health');
      state.cursor = health.cursor || 0;
      state.simulateMode = Boolean(health.simulate);
    } catch (error) {
      setLink('lost', error.message);
    }

    await Promise.all([refreshFleet(), refreshRuns(), refreshMetrics()]);
    await refreshGraph();
    renderFeed();
    connect();

    // Metrics come from files on disk, so they are polled rather than pushed.
    setInterval(refreshMetrics, 20000);
    setInterval(renderRuns, 10000);
  }

  async function refreshFleet() {
    const fleet = await api('/api/fleet');
    state.fleet = fleet;
    state.agents = new Map(fleet.agents.map((agent) => [agent.id, agent]));
    renderRoster();
    renderLaunchAgents();
    updateModePill();
    renderKpis();
  }

  async function refreshGraph() {
    const payload = await api('/api/graph');
    map.render(payload.ir);
    map.applyFilters({
      review: $('show-review').checked,
      dependency: $('show-dependency').checked,
    });
    renderLegend(payload.validation);
    for (const agent of state.agents.values()) {
      map.setAgentState(agent.id, agent.state || { status: 'idle' });
    }
  }

  async function refreshRuns() {
    const payload = await api('/api/runs?limit=40');
    state.runs = payload.runs;
    state.runsById = new Map(payload.runs.map((run) => [run.id, run]));
    for (const run of payload.runs) {
      if (run.stages?.length) state.stagesByRun.set(run.id, run.stages);
    }
    if (!state.selectedRun && payload.runs.length) selectRun(payload.runs[0].id, false);
    renderRuns();
  }

  async function refreshMetrics() {
    try {
      state.metrics = await api('/api/metrics');
      renderKpis();
      renderScores();
    } catch { /* a metrics hiccup must not blank the console */ }
  }

  /* ── event stream ──────────────────────────────────────────────────── */

  function connect() {
    if (source) source.close();
    setLink('connecting');
    source = new EventSource(withToken(`/api/events?since=${state.cursor}`));

    source.onopen = () => { retryDelay = 1000; setLink('live'); };

    source.onmessage = (message) => {
      let event;
      try { event = JSON.parse(message.data); } catch { return; }
      if (event.type === 'heartbeat') { setLink('live'); return; }
      if (event.seq) state.cursor = Math.max(state.cursor, event.seq);
      applyEvent(event);
    };

    source.onerror = () => {
      setLink('lost');
      source.close();
      // Reconnect from the last applied cursor so nothing is missed.
      setTimeout(connect, retryDelay);
      retryDelay = Math.min(retryDelay * 2, 15000);
    };
  }

  function setLink(status, detail) {
    state.link = status;
    $('link-dot').dataset.state = status;
    $('link-label').textContent = status === 'live' ? 'live' : status;
    if (detail) $('brand-sub').textContent = detail;
  }

  function applyEvent(event) {
    switch (event.type) {
      case 'fleet': {
        const agent = state.agents.get(event.agent);
        if (agent) {
          agent.state = event.state || { status: event.status };
          map.setAgentState(agent.id, agent.state);
          renderRoster();
        }
        break;
      }

      case 'run.queued':
      case 'run.started': {
        pushFeed(event, `${event.agent_name} ${event.type === 'run.queued' ? 'queued' : 'started'}`
          + (event.simulated ? ' (simulated)' : ''), 'event');
        refreshRuns().catch(() => {});
        if (event.type === 'run.started') selectRun(event.run_id, false);
        break;
      }

      case 'run.log':
        pushFeed(event, event.line, event.level || 'info');
        break;

      case 'stage.started': {
        const stages = state.stagesByRun.get(event.run_id) || [];
        stages.push({
          name: event.stage, agent: event.agent, started_at: event.ts,
          finished_at: null, status: 'running', score: null,
        });
        state.stagesByRun.set(event.run_id, stages);
        pushFeed(event, `▸ ${event.stage}${event.detail ? ` — ${event.detail}` : ''}`, 'event');
        renderTimeline();
        break;
      }

      case 'stage.finished': {
        const stages = state.stagesByRun.get(event.run_id) || [];
        for (let i = stages.length - 1; i >= 0; i -= 1) {
          if (stages[i].name === event.stage) {
            stages[i].finished_at = event.ts;
            stages[i].status = event.status;
            break;
          }
        }
        renderTimeline();
        break;
      }

      case 'metric': {
        if (event.metric === 'qa_score' && !event.rollup) {
          const stages = state.stagesByRun.get(event.run_id) || [];
          const open = stages.filter((s) => s.finished_at === null);
          const target = open.length ? open[open.length - 1] : stages[stages.length - 1];
          if (target) target.score = event.value;
          pushFeed(event, `${event.label}: ${event.value}/50`,
            event.failed ? 'warn' : 'event');
          renderTimeline();
        }
        break;
      }

      case 'artifact':
        pushFeed(event, `saved ${event.path}`, 'event');
        break;

      case 'run.finished':
      case 'run.cancelled': {
        pushFeed(event,
          `${event.agent_name} ${event.status} in ${duration(event.duration)}`,
          event.status === 'error' ? 'error' : 'event');
        refreshRuns().catch(() => {});
        refreshMetrics();
        break;
      }

      default:
        break;
    }
  }

  /* ── KPI strip ─────────────────────────────────────────────────────── */

  function renderKpis() {
    const metrics = state.metrics;
    if (!metrics) return;
    const container = $('kpis');
    container.replaceChildren();

    const ready = [...state.agents.values()]
      .filter((a) => a.dispatchable && a.readiness === 'operational').length;
    const dispatchable = [...state.agents.values()].filter((a) => a.dispatchable).length;

    const tiles = [
      ['active runs', String(metrics.runs_active), null],
      ['qa average', metrics.qa_average === null ? '—' : metrics.qa_average.toFixed(1),
        '/50', metrics.qa_timeline],
      ['topics', String(metrics.topics), null],
      ['artifacts', String(metrics.artifacts_logged), null],
      ['est. spend', `$${metrics.estimated_spend_usd.toFixed(2)}`, null],
      ['agents ready', `${ready}`, `/${dispatchable}`],
    ];

    for (const [label, value, unit, series] of tiles) {
      const tile = node('div', 'kpi');
      tile.appendChild(node('span', 'kpi-label', label));
      const figure = node('span', 'kpi-value', value);
      if (unit) {
        const suffix = node('span', 'unit', unit);
        figure.appendChild(suffix);
      }
      tile.appendChild(figure);
      if (series && series.length > 1) tile.appendChild(sparkline(series));
      container.appendChild(tile);
    }
  }

  /* Single-series sparkline: QA score over the last runs. No legend needed —
     the tile label names the series. */
  function sparkline(series) {
    const width = 84;
    const height = 18;
    const scores = series.map((point) => point.score);
    const min = Math.min(...scores, 30);
    const max = Math.max(...scores, 50);
    const span = Math.max(1, max - min);

    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'kpi-spark');
    svg.setAttribute('width', width);
    svg.setAttribute('height', height);
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.setAttribute('aria-hidden', 'true');

    const points = scores.map((score, index) => {
      const x = scores.length === 1 ? width : (index / (scores.length - 1)) * width;
      const y = height - 2 - ((score - min) / span) * (height - 4);
      return [x, y];
    });

    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', points.map((p, i) => `${i ? 'L' : 'M'} ${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' '));
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', 'var(--accent)');
    path.setAttribute('stroke-width', '2');
    path.setAttribute('stroke-linejoin', 'round');
    path.setAttribute('stroke-linecap', 'round');
    svg.appendChild(path);

    const last = points[points.length - 1];
    const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    dot.setAttribute('cx', last[0].toFixed(1));
    dot.setAttribute('cy', last[1].toFixed(1));
    dot.setAttribute('r', '2.4');
    dot.setAttribute('fill', 'var(--accent)');
    svg.appendChild(dot);
    return svg;
  }

  /* ── roster ────────────────────────────────────────────────────────── */

  function renderRoster() {
    if (!state.fleet) return;
    const container = $('roster');
    const onlyLive = $('only-live').checked;
    container.replaceChildren();

    for (const squad of state.fleet.squads) {
      const members = [...state.agents.values()].filter((a) => a.squad === squad.id);
      const visible = onlyLive
        ? members.filter((a) => ['running', 'queued'].includes(a.state?.status))
        : members;
      if (!visible.length) continue;

      const block = node('div', 'squad-block');
      const heading = node('div', 'squad-label');
      const swatch = node('span', 'squad-swatch');
      swatch.style.background = squad.accent;
      heading.append(swatch, node('span', null, squad.name));
      block.appendChild(heading);

      for (const agent of visible) {
        const row = node('button', 'agent-row');
        row.type = 'button';
        row.setAttribute('aria-current', String(state.selectedAgent === agent.id));
        row.appendChild(node('span', 'agent-glyph', agent.glyph));

        const middle = node('span');
        middle.appendChild(node('span', 'agent-name', agent.name));
        const status = agent.state?.status || 'idle';
        const sub = status === 'idle' && agent.readiness === 'unconfigured'
          ? 'needs credentials'
          : agent.summary;
        middle.appendChild(node('span', 'agent-sub', truncate(sub, 34)));
        middle.style.display = 'grid';
        row.appendChild(middle);

        const badge = node('span', 'status',
          agent.readiness === 'unconfigured' && status === 'idle' ? 'dark' : status);
        badge.dataset.status = agent.readiness === 'unconfigured' && status === 'idle'
          ? 'unconfigured' : status;
        row.appendChild(badge);

        row.addEventListener('click', () => {
          state.selectedAgent = state.selectedAgent === agent.id ? null : agent.id;
          map.setSelected(state.selectedAgent);
          renderRoster();
          if (state.selectedAgent) openDrawer(agent.id); else closeDrawer();
        });
        block.appendChild(row);
      }
      container.appendChild(block);
    }

    if (!container.children.length) {
      container.appendChild(node('p', 'empty', 'No agents match this filter.'));
    }
  }

  const truncate = (text, max) => (text.length > max ? `${text.slice(0, max - 1)}…` : text);

  /* ── legend ────────────────────────────────────────────────────────── */

  function renderLegend(validation) {
    const legend = $('map-legend');
    legend.replaceChildren();
    const entries = [
      ['', 'work'],
      ['review', 'QA review'],
      ['dependency', 'external call'],
    ];
    for (const [cls, label] of entries) {
      const item = node('span', 'legend-item');
      const swatch = node('span', `legend-swatch ${cls}`.trim());
      item.append(swatch, node('span', null, label));
      legend.appendChild(item);
    }
    const verdict = node('span', 'legend-item',
      validation.ok
        ? `map validated · ${validation.warnings.length} warning(s)`
        : `map invalid · ${validation.errors.length} error(s)`);
    legend.appendChild(verdict);
  }

  /* ── launch console ────────────────────────────────────────────────── */

  function renderLaunchAgents() {
    const select = $('launch-agent');
    const previous = select.value;
    select.replaceChildren();

    for (const squad of state.fleet.squads) {
      const members = [...state.agents.values()]
        .filter((a) => a.squad === squad.id && a.dispatchable);
      if (!members.length) continue;
      const group = document.createElement('optgroup');
      group.label = squad.name;
      for (const agent of members) {
        const option = document.createElement('option');
        option.value = agent.id;
        option.textContent = agent.name;
        group.appendChild(option);
      }
      select.appendChild(group);
    }

    select.value = previous || 'mission';
    if (!select.value) select.selectedIndex = 0;
    renderLaunchParams();
  }

  function renderLaunchParams() {
    const agent = state.agents.get($('launch-agent').value);
    const container = $('launch-params');
    container.replaceChildren();
    $('launch-error').textContent = '';
    if (!agent) return;

    $('launch-blurb').textContent = agent.summary;

    if (agent.readiness === 'unconfigured') {
      const note = node('p', 'blocked-note',
        `Needs ${agent.missing_env.join(', ')} — simulate to rehearse it.`);
      container.appendChild(note);
      $('launch-simulate').checked = true;
    } else {
      $('launch-simulate').checked = state.simulateMode;
    }

    for (const param of agent.params) {
      if (param.kind === 'flag') {
        const label = node('label', 'field flag-field');
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.dataset.param = param.name;
        input.checked = Boolean(param.default);
        label.append(input, node('span', null, param.label));
        container.appendChild(label);
        continue;
      }

      const label = node('label', 'field');
      label.appendChild(node('span', null,
        param.label + (param.required ? ' *' : '')));

      let input;
      if (param.kind === 'choice') {
        input = document.createElement('select');
        if (!param.required) {
          const blank = document.createElement('option');
          blank.value = '';
          blank.textContent = '—';
          input.appendChild(blank);
        }
        for (const choice of param.choices) {
          const option = document.createElement('option');
          option.value = choice;
          option.textContent = choice;
          input.appendChild(option);
        }
      } else {
        input = document.createElement('input');
        input.type = param.kind === 'int' ? 'number' : 'text';
      }
      input.dataset.param = param.name;
      if (param.default !== null && param.default !== undefined) {
        input.value = param.default;
      }
      if (param.required) input.required = true;
      label.appendChild(input);
      if (param.help) label.appendChild(node('p', 'field-help', param.help));
      container.appendChild(label);
    }
  }

  async function launch(event) {
    event.preventDefault();
    const button = $('launch-button');
    const error = $('launch-error');
    error.textContent = '';

    const agentId = $('launch-agent').value;
    const params = {};
    for (const input of $('launch-params').querySelectorAll('[data-param]')) {
      const name = input.dataset.param;
      if (input.type === 'checkbox') {
        if (input.checked) params[name] = true;
      } else if (input.value !== '') {
        params[name] = input.value;
      }
    }

    button.disabled = true;
    button.textContent = 'Deploying…';
    try {
      const payload = await api('/api/runs', {
        method: 'POST',
        body: JSON.stringify({
          agent: agentId,
          params,
          simulate: $('launch-simulate').checked,
        }),
      });
      selectRun(payload.run.id, false);
      await refreshRuns();
    } catch (failure) {
      error.textContent = failure.message;
    } finally {
      button.disabled = false;
      button.textContent = 'Deploy agent';
    }
  }

  function updateModePill() {
    const pill = $('mode-pill');
    pill.dataset.mode = state.simulateMode ? 'simulation' : 'live';
    pill.textContent = state.simulateMode ? 'simulation' : 'live';
    $('brand-sub').textContent = state.simulateMode
      ? 'simulation mode — no API calls, no writes'
      : `${state.agents.size} agents under command`;
  }

  /* ── runs ──────────────────────────────────────────────────────────── */

  function renderRuns() {
    const container = $('runs');
    container.replaceChildren();

    if (!state.runs.length) {
      container.appendChild(node('p', 'empty', 'Nothing has run yet.'));
      $('runs-note').textContent = '';
      return;
    }

    const active = state.runs.filter((r) => ['queued', 'running'].includes(r.status));
    $('runs-note').textContent = active.length ? `${active.length} active` : '';

    for (const run of state.runs.slice(0, 25)) {
      const row = node('button', 'run-row');
      row.type = 'button';
      row.setAttribute('aria-current', String(state.selectedRun === run.id));

      const title = node('span', 'run-title', run.agent_name);
      row.appendChild(title);

      if (['queued', 'running'].includes(run.status)) {
        const cancel = node('button', 'run-cancel', 'stop');
        cancel.type = 'button';
        cancel.addEventListener('click', async (event) => {
          event.stopPropagation();
          try { await api(`/api/runs/${run.id}/cancel`, { method: 'POST' }); }
          catch { /* the run finished on its own */ }
        });
        row.appendChild(cancel);
      } else {
        const badge = node('span', 'status', run.status);
        badge.dataset.status = run.status;
        row.appendChild(badge);
      }

      const topic = run.params?.topic ? `${run.params.topic} · ` : '';
      const when = run.started_at ? ago(run.started_at) : 'queued';
      const sim = run.simulated ? ' · sim' : '';
      row.appendChild(node('span', 'run-meta', `${topic}${when}${sim}`));

      row.addEventListener('click', () => selectRun(run.id, true));
      container.appendChild(row);
    }
  }

  async function selectRun(runId, scrollFeed) {
    state.selectedRun = runId;
    renderRuns();
    renderTimeline();
    if (!state.stagesByRun.has(runId)) {
      try {
        const detail = await api(`/api/runs/${runId}`);
        // Live events may have filled the stage list while this was in flight.
        if (!state.stagesByRun.has(runId)) {
          state.stagesByRun.set(runId, detail.stages || []);
        }
        if (scrollFeed && detail.log?.length) {
          state.feed = detail.log.map((entry) => ({
            ts: entry.ts, agent: detail.agent_name, text: entry.line, level: entry.level,
          }));
          renderFeed();
        }
        renderTimeline();
      } catch { /* run may have aged out of history */ }
    }
  }

  /* ── timeline ──────────────────────────────────────────────────────── */

  function renderTimeline() {
    const container = $('timeline');
    const runId = state.selectedRun;
    const stages = runId ? state.stagesByRun.get(runId) || [] : [];
    const run = state.runsById.get(runId);

    container.replaceChildren();
    $('timeline-note').textContent = run
      ? `${run.agent_name}${run.params?.topic ? ` · ${run.params.topic}` : ''}`
      : 'no run selected';

    if (!stages.length) {
      container.appendChild(node('p', 'empty',
        run ? 'Waiting for the first stage…' : 'Select a run to see its stages.'));
      return;
    }

    const now = Date.now() / 1000;
    const start = Math.min(...stages.map((s) => s.started_at || now));
    const end = Math.max(...stages.map((s) => s.finished_at || now));
    const span = Math.max(1, end - start);

    for (const stage of stages) {
      const row = node('div', 'timeline-row');
      row.appendChild(node('span', 'timeline-name', stage.name));

      const track = node('div', 'timeline-track');
      const bar = node('div', 'timeline-bar');
      const from = ((stage.started_at || start) - start) / span;
      const to = ((stage.finished_at || now) - start) / span;
      bar.style.left = `${(from * 100).toFixed(2)}%`;
      bar.style.width = `${Math.max(1.5, (to - from) * 100).toFixed(2)}%`;
      bar.dataset.status = stage.status || 'running';
      track.appendChild(bar);
      row.appendChild(track);

      const elapsed = (stage.finished_at || now) - (stage.started_at || now);
      row.appendChild(node('span', 'timeline-meta',
        stage.score ? `${stage.score}/50` : duration(elapsed)));
      container.appendChild(row);
    }
  }

  /* ── feed ──────────────────────────────────────────────────────────── */

  function pushFeed(event, text, level) {
    const agent = state.agents.get(event.agent);
    state.feed.push({
      ts: event.ts,
      agent: agent ? agent.name : event.agent || 'commander',
      text,
      level,
    });
    if (state.feed.length > MAX_FEED) state.feed.splice(0, state.feed.length - MAX_FEED);
    appendFeedLine(state.feed[state.feed.length - 1]);
  }

  function feedVisible(entry) {
    if (state.feedFilter === 'all') return true;
    if (state.feedFilter === 'event') return entry.level === 'event';
    return entry.level === 'warn' || entry.level === 'error';
  }

  function appendFeedLine(entry) {
    const container = $('feed');
    const placeholder = container.querySelector('.feed-empty');
    if (placeholder) placeholder.remove();
    if (!feedVisible(entry)) return;

    const line = node('div', 'feed-line');
    line.dataset.level = entry.level;
    line.append(
      node('span', 'feed-time', clock(entry.ts)),
      node('span', 'feed-agent', entry.agent),
      node('span', 'feed-text', entry.text),
    );
    container.appendChild(line);
    while (container.children.length > MAX_FEED) container.firstChild.remove();
    if (state.follow) container.scrollTop = container.scrollHeight;
  }

  function renderFeed() {
    const container = $('feed');
    container.replaceChildren();
    const visible = state.feed.filter(feedVisible);
    if (!visible.length) {
      container.appendChild(node('p', 'feed-empty', 'Nothing on the wire yet.'));
      return;
    }
    for (const entry of visible) appendFeedLine(entry);
  }

  /* ── QA by agent ───────────────────────────────────────────────────── */

  function renderScores() {
    const container = $('scores');
    container.replaceChildren();
    const byAgent = state.metrics?.qa_by_agent || {};
    const rows = Object.entries(byAgent).filter(([, value]) => value !== null);

    if (!rows.length) {
      container.appendChild(node('p', 'empty', 'No QA scores logged yet.'));
      return;
    }

    rows.sort((a, b) => b[1] - a[1]);
    for (const [name, average] of rows) {
      const row = node('div', 'score-row');
      row.appendChild(node('span', 'score-name', name.replace(/ Agent.*$/, '')));
      const track = node('div', 'score-track');
      const bar = node('div', 'score-bar');
      bar.style.width = `${Math.min(100, (average / 50) * 100).toFixed(1)}%`;
      track.appendChild(bar);
      row.appendChild(track);
      row.appendChild(node('span', 'score-value', average.toFixed(1)));
      container.appendChild(row);
    }
  }

  /* ── drawer ────────────────────────────────────────────────────────── */

  function openDrawer(agentId) {
    const agent = state.agents.get(agentId);
    if (!agent) return;

    $('drawer-title').textContent = agent.name;
    const body = $('drawer-body');
    body.replaceChildren();
    body.appendChild(node('p', null, agent.summary));
    if (agent.doc) body.appendChild(node('p', null, agent.doc));

    const list = document.createElement('dl');
    const facts = [
      ['squad', state.fleet.squads.find((s) => s.id === agent.squad)?.name || agent.squad],
      ['kind', agent.kind],
      ['status', agent.state?.status || 'idle'],
      ['readiness', agent.readiness],
    ];
    if (agent.state?.detail) facts.push(['last', agent.state.detail]);
    if (agent.state?.last_score) facts.push(['last QA', `${agent.state.last_score}/50`]);
    for (const [term, value] of facts) {
      list.appendChild(node('dt', null, term));
      list.appendChild(node('dd', null, String(value)));
    }
    body.appendChild(list);

    if (agent.missing_env.length) {
      const chips = node('div', 'chip-row');
      for (const key of agent.missing_env) {
        const chip = node('span', 'chip', key);
        chip.dataset.tone = 'warn';
        chips.appendChild(chip);
      }
      body.appendChild(node('p', null, 'Missing credentials:'));
      body.appendChild(chips);
    }

    if (agent.dispatchable) {
      const button = node('button', 'launch-button', `Load ${agent.name} into launcher`);
      button.type = 'button';
      button.addEventListener('click', () => {
        $('launch-agent').value = agent.id;
        renderLaunchParams();
        closeDrawer();
        $('launch-agent').focus();
      });
      body.appendChild(button);
    }

    $('drawer').hidden = false;
  }

  function closeDrawer() {
    $('drawer').hidden = true;
    if (state.selectedAgent) {
      state.selectedAgent = null;
      map.setSelected(null);
      renderRoster();
    }
  }

  /* ── controls ──────────────────────────────────────────────────────── */

  function bindControls() {
    $('launch-form').addEventListener('submit', launch);
    $('launch-agent').addEventListener('change', renderLaunchParams);
    $('only-live').addEventListener('change', renderRoster);

    $('show-review').addEventListener('change', (event) => {
      map.applyFilters({ review: event.target.checked });
    });
    $('show-dependency').addEventListener('change', (event) => {
      map.applyFilters({ dependency: event.target.checked });
    });

    $('zoom-in').addEventListener('click', () => map.zoom(0.82));
    $('zoom-out').addEventListener('click', () => map.zoom(1.22));
    $('zoom-fit').addEventListener('click', () => map.fit());

    $('follow').addEventListener('change', (event) => {
      state.follow = event.target.checked;
    });
    $('feed-filter').addEventListener('change', (event) => {
      state.feedFilter = event.target.value;
      renderFeed();
    });

    $('drawer-close').addEventListener('click', closeDrawer);
    $('drawer-scrim').addEventListener('click', closeDrawer);
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !$('drawer').hidden) closeDrawer();
    });

    window.addEventListener('resize', () => {
      if (map?.ir) map.fit();
    });
  }

  boot().catch((error) => {
    setLink('lost', error.message);
    $('feed').appendChild(node('p', 'feed-empty', `Failed to start: ${error.message}`));
  });
})();
