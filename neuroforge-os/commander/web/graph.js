/* Fleet map renderer.
 *
 * Draws the validated IR the server produced and nothing more — no layout
 * decisions happen here, so what you see is exactly what the validator
 * checked. The renderer only owns presentation: zoom, pan, hover tracing,
 * edge-class filtering and live status.
 */

const SVG_NS = 'http://www.w3.org/2000/svg';
const CORNER_RADIUS = 9;

function el(name, attrs = {}, parent = null) {
  const node = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attrs)) {
    if (value !== null && value !== undefined) node.setAttribute(key, String(value));
  }
  if (parent) parent.appendChild(node);
  return node;
}

/* Orthogonal polyline with rounded corners. */
function orthPath(points, radius = CORNER_RADIUS) {
  if (points.length < 2) return '';
  let d = `M ${points[0][0]} ${points[0][1]}`;
  for (let i = 1; i < points.length - 1; i += 1) {
    const [px, py] = points[i - 1];
    const [cx, cy] = points[i];
    const [nx, ny] = points[i + 1];
    const inLen = Math.hypot(cx - px, cy - py);
    const outLen = Math.hypot(nx - cx, ny - cy);
    const r = Math.min(radius, inLen / 2, outLen / 2);
    if (r < 1) { d += ` L ${cx} ${cy}`; continue; }
    const ax = cx - ((cx - px) / (inLen || 1)) * r;
    const ay = cy - ((cy - py) / (inLen || 1)) * r;
    const bx = cx + ((nx - cx) / (outLen || 1)) * r;
    const by = cy + ((ny - cy) / (outLen || 1)) * r;
    d += ` L ${ax} ${ay} Q ${cx} ${cy} ${bx} ${by}`;
  }
  const last = points[points.length - 1];
  return `${d} L ${last[0]} ${last[1]}`;
}

function curvePath(points) {
  const [a, c1, c2, b] = points;
  return `M ${a[0]} ${a[1]} C ${c1[0]} ${c1[1]}, ${c2[0]} ${c2[1]}, ${b[0]} ${b[1]}`;
}

function truncate(text, max) {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

class FleetMap {
  constructor(svg, shell, { onSelect } = {}) {
    this.svg = svg;
    this.shell = shell;
    this.onSelect = onSelect || (() => {});
    this.ir = null;
    this.nodeEls = new Map();
    this.edgeEls = new Map();
    this.view = { x: 0, y: 0, w: 100, h: 100 };
    this.selected = null;
    this.filters = { review: true, dependency: false };
    this._bindInteractions();
  }

  /* ── rendering ───────────────────────────────────────────────────── */

  render(ir) {
    this.ir = ir;
    this.svg.replaceChildren();
    this.nodeEls.clear();
    this.edgeEls.clear();

    this.svg.setAttribute('width', '100%');
    this.svg.setAttribute('height', '100%');
    this.svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');

    this._defs();
    this.root = el('g', { class: 'map-root' }, this.svg);

    this._drawLanes();
    this.edgeLayer = el('g', { class: 'edge-layer' }, this.root);
    this.labelLayer = el('g', { class: 'label-layer' }, this.root);
    this.nodeLayer = el('g', { class: 'node-layer' }, this.root);

    ir.edges.forEach((edge) => this._drawEdge(edge));
    ir.nodes.forEach((node) => this._drawNode(node));

    this.applyFilters(this.filters);
    this.fit();
  }

  _defs() {
    const defs = el('defs', {}, this.svg);
    const markers = [
      ['arrow-flow', 'var(--rule)'],
      ['arrow-active', 'var(--accent)'],
      ['arrow-review', 'var(--serious)'],
      ['arrow-dependency', 'var(--ink-muted)'],
    ];
    for (const [id, fill] of markers) {
      const marker = el('marker', {
        id, viewBox: '0 0 8 8', refX: 7, refY: 4,
        markerWidth: 6, markerHeight: 6, orient: 'auto-start-reverse',
      }, defs);
      el('path', { d: 'M 0 0 L 8 4 L 0 8 z', fill }, marker);
    }
  }

  _drawLanes() {
    const layer = el('g', { class: 'lane-layer' }, this.root);
    for (const lane of this.ir.lanes) {
      el('line', {
        class: 'lane-rule',
        x1: lane.x, y1: lane.y + 7, x2: lane.x + 26, y2: lane.y + 7,
        stroke: lane.accent,
      }, layer);
      const text = el('text', {
        class: 'lane-head', x: lane.x + 34, y: lane.y + 11,
      }, layer);
      text.textContent = lane.name.toUpperCase();
    }
  }

  _drawEdge(edge) {
    const path = el('path', {
      class: 'edge',
      'data-kind': edge.kind,
      'data-from': edge.from,
      'data-to': edge.to,
      d: edge.render === 'curve' ? curvePath(edge.points) : orthPath(edge.points),
      'marker-end': `url(#arrow-${edge.kind === 'flow' ? 'flow' : edge.kind})`,
    }, this.edgeLayer);
    this.edgeEls.set(edge.id, { el: path, edge });

    if (edge.label && edge.label_point) {
      const [lx, ly] = edge.label_point;
      const width = Math.max(28, edge.label.length * 5.8) + 12;
      el('rect', {
        class: 'edge-label-bg',
        x: lx - width / 2, y: ly - 7.5, width, height: 15, rx: 4,
      }, this.labelLayer);
      const text = el('text', { class: 'edge-label', x: lx, y: ly }, this.labelLayer);
      text.textContent = edge.label;
    }
  }

  _drawNode(node) {
    const group = el('g', {
      class: 'node',
      'data-id': node.id,
      'data-status': node.state?.status || 'idle',
      'data-readiness': node.readiness,
      transform: `translate(${node.x} ${node.y})`,
    }, this.nodeLayer);

    const hit = el('g', {
      class: 'node-hit',
      tabindex: '0',
      role: 'button',
      'aria-label': `${node.label} — ${node.summary}`,
    }, group);

    el('rect', {
      class: 'node-halo',
      x: -3, y: -3, width: node.w + 6, height: node.h + 6, rx: 10,
      style: 'transform-origin: center; transform-box: fill-box;',
    }, hit);

    el('rect', {
      class: 'node-box', x: 0, y: 0, width: node.w, height: node.h, rx: 8,
    }, hit);

    // Squad hue lives on a thin strip; it never encodes status.
    el('rect', {
      x: 0, y: 0, width: 3.5, height: node.h, rx: 1.5, fill: node.accent,
    }, hit);

    const glyph = el('text', {
      class: 'node-glyph', x: 14, y: 24, fill: node.accent,
    }, hit);
    glyph.textContent = node.glyph;

    const label = el('text', { class: 'node-label', x: 34, y: 24 }, hit);
    label.textContent = truncate(node.label, 20);

    const status = el('text', { class: 'node-status', x: 14, y: 42 }, hit);
    status.textContent = this._statusText(node.state, node.readiness);
    this.nodeEls.set(node.id, { group, status, node });

    const title = el('title', {}, hit);
    title.textContent = `${node.label}\n${node.summary}`;

    hit.addEventListener('click', () => this.select(node.id));
    hit.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        this.select(node.id);
      }
    });
    hit.addEventListener('pointerenter', () => this._trace(node.id));
    hit.addEventListener('pointerleave', () => this._trace(this.selected));
  }

  _statusText(state, readiness) {
    const status = state?.status || 'idle';
    if (status === 'idle' && readiness === 'unconfigured') return 'no credentials';
    const detail = state?.detail;
    if (detail && status === 'running') return truncate(detail, 24);
    if (state?.last_score && (status === 'ok' || status === 'warn')) {
      return `${status} · ${state.last_score}/50`;
    }
    return status;
  }

  /* ── live updates ────────────────────────────────────────────────── */

  setAgentState(agentId, state) {
    const entry = this.nodeEls.get(agentId);
    if (!entry) return;
    entry.node.state = state;
    entry.group.setAttribute('data-status', state.status || 'idle');
    entry.status.textContent = this._statusText(state, entry.node.readiness);
    this._refreshActiveEdges();
  }

  _refreshActiveEdges() {
    const live = new Set();
    for (const [id, entry] of this.nodeEls) {
      if (entry.node.state?.status === 'running') live.add(id);
    }
    for (const { el: path, edge } of this.edgeEls.values()) {
      // An edge is "carrying work" when its downstream end is running.
      const active = live.has(edge.to) && edge.kind === 'flow';
      if (active) path.setAttribute('data-active', 'true');
      else path.removeAttribute('data-active');
    }
  }

  /* ── interaction ─────────────────────────────────────────────────── */

  select(agentId) {
    this.selected = this.selected === agentId ? null : agentId;
    this._trace(this.selected);
    this.onSelect(this.selected);
  }

  setSelected(agentId) {
    this.selected = agentId;
    this._trace(agentId);
  }

  _trace(agentId) {
    const root = this.root;
    if (!root) return;
    root.classList.toggle('map-dim', Boolean(agentId));
    for (const { group } of this.nodeEls.values()) group.classList.remove('related');
    for (const { el: path } of this.edgeEls.values()) path.classList.remove('related');
    if (!agentId) return;

    const related = new Set([agentId]);
    for (const { el: path, edge } of this.edgeEls.values()) {
      if (edge.from === agentId || edge.to === agentId) {
        path.classList.add('related');
        related.add(edge.from);
        related.add(edge.to);
      }
    }
    for (const id of related) this.nodeEls.get(id)?.group.classList.add('related');
  }

  applyFilters(filters) {
    this.filters = { ...this.filters, ...filters };
    for (const { el: path, edge } of this.edgeEls.values()) {
      const visible = edge.kind === 'flow'
        || (edge.kind === 'review' && this.filters.review)
        || (edge.kind === 'dependency' && this.filters.dependency);
      path.style.display = visible ? '' : 'none';
    }
  }

  /* ── viewport ────────────────────────────────────────────────────── */

  fit() {
    if (!this.ir) return;
    const pad = 16;
    this._setView({
      x: -pad, y: -pad,
      w: this.ir.width + pad * 2,
      h: this.ir.height + pad * 2,
    });
  }

  zoom(factor, origin) {
    const { x, y, w, h } = this.view;
    const nw = Math.max(240, Math.min(this.ir.width * 3, w * factor));
    const nh = nw * (h / w);
    const ox = origin ? origin.x : x + w / 2;
    const oy = origin ? origin.y : y + h / 2;
    this._setView({
      x: ox - ((ox - x) * nw) / w,
      y: oy - ((oy - y) * nh) / h,
      w: nw, h: nh,
    });
  }

  _setView(view) {
    this.view = view;
    this.svg.setAttribute(
      'viewBox',
      `${view.x.toFixed(1)} ${view.y.toFixed(1)} ${view.w.toFixed(1)} ${view.h.toFixed(1)}`,
    );
  }

  _toUser(event) {
    const rect = this.svg.getBoundingClientRect();
    if (!rect.width || !rect.height) return { x: 0, y: 0 };
    // preserveAspectRatio meet: the shorter axis is letterboxed.
    const scale = Math.max(this.view.w / rect.width, this.view.h / rect.height);
    const offsetX = (rect.width - this.view.w / scale) / 2;
    const offsetY = (rect.height - this.view.h / scale) / 2;
    return {
      x: this.view.x + (event.clientX - rect.left - offsetX) * scale,
      y: this.view.y + (event.clientY - rect.top - offsetY) * scale,
    };
  }

  _bindInteractions() {
    let dragging = null;

    this.shell.addEventListener('pointerdown', (event) => {
      if (event.target.closest('.node-hit')) return;
      dragging = { x: event.clientX, y: event.clientY, view: { ...this.view } };
      this.shell.classList.add('dragging');
      this.shell.setPointerCapture(event.pointerId);
    });

    this.shell.addEventListener('pointermove', (event) => {
      if (!dragging) return;
      const rect = this.svg.getBoundingClientRect();
      const scale = this.view.w / (rect.width || 1);
      this._setView({
        ...this.view,
        x: dragging.view.x - (event.clientX - dragging.x) * scale,
        y: dragging.view.y - (event.clientY - dragging.y) * scale,
      });
    });

    const endDrag = (event) => {
      if (!dragging) return;
      dragging = null;
      this.shell.classList.remove('dragging');
      try { this.shell.releasePointerCapture(event.pointerId); } catch { /* ignore */ }
    };
    this.shell.addEventListener('pointerup', endDrag);
    this.shell.addEventListener('pointercancel', endDrag);

    this.shell.addEventListener('wheel', (event) => {
      if (!this.ir) return;
      event.preventDefault();
      this.zoom(event.deltaY > 0 ? 1.12 : 0.89, this._toUser(event));
    }, { passive: false });
  }
}

window.FleetMap = FleetMap;
