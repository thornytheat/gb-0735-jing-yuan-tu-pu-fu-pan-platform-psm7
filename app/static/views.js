export const q = (selector, root = document) => root.querySelector(selector);
export const text = (selector, value) => { q(selector).textContent = value ?? '—'; };
export const vector = (point) => point ? `(${point.join(', ')})` : '—';
export const number = (value) => value == null ? '—' : Number(value).toLocaleString('zh-CN');
export function feedback(message, error = false) {
  const panel = q('#feedback');
  panel.hidden = !message;
  panel.classList.toggle('error', error);
  panel.textContent = message ?? '';
}
export const labels = {
  PASS: '通过', FAIL: '失败', PENDING: '待测', CONFLICT: '冲突', ACTIVE: '有效芯粒',
  EDGE_EXCLUSION: '边缘保留带', NOTCH_VOID: '缺口空位', OUTSIDE_DISC: '圆片外',
  OUT_OF_GRID: '超出阵列', MATCH: '一致', REVIEW: '台账有差异', DIFFERENCE: '有差异',
  MISSING_REFERENCE: '缺交接台账', UNBALANCED: '阵列或行数失衡',
  ADMIT: '可入批', HOLD: '待补证', REJECT: '不可入批',
  FULL: '整片有证据', PARTIAL: '部分有证据', NONE: '无证据',
  UNVERIFIED: '无证据不可核验',
};

export function element(tag, value, className) {
  const item = document.createElement(tag);
  if (value != null) item.textContent = value;
  if (className) item.className = className;
  return item;
}

export function options(select, choices, value) {
  select.replaceChildren(...choices.map(([id, title]) => new Option(title, id)));
  if (choices.some(([id]) => id === value)) select.value = value;
}

export function pairs(items) {
  const list = element('dl', null, 'pairs');
  for (const [title, value] of items) {
    const content = element('dd', null, 'mono');
    content.append(value instanceof Node ? value : String(value ?? '—'));
    list.append(element('dt', title), content);
  }
  return list;
}

export function status(code) {
  const variant = {PASS:'pass', FAIL:'fail', CONFLICT:'conflict', PENDING:'pending', MATCH:'pass',
    REVIEW:'pending', DIFFERENCE:'pending', UNBALANCED:'fail',
    ADMIT:'pass', HOLD:'pending', REJECT:'fail', FULL:'pass', PARTIAL:'pending', NONE:'fail',
    UNVERIFIED:'pending'}[code] ?? '';
  return element('span', labels[code] ?? code, `status ${variant}`);
}

export function failure(box, error) {
  box.replaceChildren(element('p', error.message || '请求失败，请重试。', 'inline-error'));
}

function table(box, records, columns, empty = '没有符合条件的记录。') {
  if (records.length === 0) {
    box.replaceChildren(element('p', empty, 'empty'));
    return;
  }
  const grid = element('table', null, 'ledger');
  const headers = grid.createTHead().insertRow();
  for (const [name, , css] of columns) {
    const th = element('th', name, css);
    th.scope = 'col';
    headers.append(th);
  }
  const body = grid.createTBody();
  for (const record of records) {
    const row = body.insertRow();
    for (const [, value, css] of columns) {
      const cell = row.insertCell();
      const item = typeof value === 'function' ? value(record) : record[value];
      if (css) cell.className = css;
      if (item instanceof Node) cell.append(item);
      else {
        cell.textContent = item ?? '—';
        cell.title = cell.textContent;
      }
    }
  }
  box.replaceChildren(grid);
}

function rowButton(label, action) {
  const button = element('button', label, 'row-link');
  button.type = 'button';
  button.addEventListener('click', () => {
    for (const peer of button.closest('tbody').querySelectorAll('[aria-pressed]')) peer.setAttribute('aria-pressed', 'false');
    button.setAttribute('aria-pressed', 'true');
    action();
  });
  button.setAttribute('aria-pressed', 'false');
  return button;
}

const original = (row) => row.fields ? vector([row.fields.x, row.fields.y]) : '—';
const line = (row) => row.end_line === row.line ? row.line : `${row.line}–${row.end_line}`;
const issueColumns = [
  ['图档', 'source', 'mono'], ['行号', line, 'num'], ['晶圆', 'wafer', 'mono'],
  ['原因码', 'code', 'mono'], ['原因', 'reason'], ['原始字段', (row) => row.raw.map((value) => JSON.stringify(value)).join(' · ')],
];

function evidenceCard(row) {
  const card = element('article', null, 'evidence-row');
  const header = element('div', null, 'evidence-id');
  header.append(element('strong', `${row.source}:${line(row)}`, 'mono'), element('span', row.code ?? '采信'));
  const fields = row.fields;
  const measurement = fields ? `${original(row)}   T${fields.attempt}   ${fields.result || '∅'}   BIN ${fields.bin || '∅'}` : '';
  card.append(header, element('p', measurement, 'evidence-values'));
  if (row.transform) {
    const {translated, mirrored, turn_degrees, canonical} = row.transform;
    card.append(element('p', `轴向 ${vector(translated)} · 镜像 ${vector(mirrored)} · ${turn_degrees}° → ${vector(canonical)}`, 'evidence-note'));
  }
  if (fields?.note) card.append(element('p', fields.note, 'evidence-note'));
  return card;
}

export function renderCell(box, cell) {
  const decision = cell.decision;
  const heading = element('div', null, 'detail-title');
  heading.append(element('strong', vector([cell.x, cell.y])), status(decision?.result ?? cell.eligibility));
  if (cell.cluster) heading.append(element('span', cell.cluster, 'mono'));
  box.replaceChildren(heading, pairs([['晶圆', cell.wafer], ['测次', decision?.attempt], ['分档', decision?.bin], ['原始行', cell.evidence.length]]));
  if (decision?.history.length) {
    const history = decision.history.map((item) => `T${item.attempt} ${labels[item.result]}`).join(' → ');
    box.append(element('p', history, 'data-strip detail-group'));
  }
  for (const row of cell.evidence) box.append(evidenceCard(row));
  if (!cell.evidence.length) box.append(element('p', '该位置暂无原始行。', 'empty'));
}

async function intake({api, base}) {
  const data = await api(`${base}/intake`);
  text('#source-total', `${data.files.length} 档`);
  table(q('#intake-files'), data.files, [
    ['图档', 'name', 'mono'], ['编码', 'encoding', 'mono'], ['段', 'segments', 'num'],
    ['物理行', 'physical_lines', 'num'], ['数据记录', 'data_count', 'num'],
  ]);
  q('#intake-summary').replaceChildren(pairs([
    ['数据记录', data.files.reduce((sum, file) => sum + file.data_count, 0)],
    ['重复档头', data.issues.filter((row) => row.bucket === 'header').length],
    ['空记录', data.issues.filter((row) => row.bucket === 'blank').length],
    ['栏数不符', data.issues.filter((row) => row.code === 'COLUMN_COUNT').length],
  ]));
  table(q('#intake-issues'), data.issues, issueColumns);
}

async function coordinates({api, base, signal}) {
  const data = await api(`${base}/coordinates`);
  table(q('#coordinate-sources'), data.sources, [
    ['图档', 'name', 'mono'], ['原点', (s) => vector([s.origin_x, s.origin_y]), 'num'],
    ['原缺口', 'notch', 'mono'], ['原轴向', (s) => `${s.x_left ? 'X←' : 'X→'} / ${s.y_down ? 'Y↓' : 'Y↑'}`],
    ['镜像', (s) => s.mirror ? 'X 反射' : '—'], ['对表', 'aligned', 'num'],
  ]);
  const form = q('#probe-form');
  const choices = data.sources.map((s) => [s.name, s.name]);
  options(form.elements.source, choices, choices.at(-1)?.[0]);
  const drawProbe = async () => {
    const target = q('#probe-output');
    const button = q('button', form);
    button.disabled = true;
    try {
      const result = await api(`${base}/coordinates/probe?${new URLSearchParams(new FormData(form))}`);
      target.replaceChildren(pairs([['平移与轴向', vector(result.translated)], ['镜像后', vector(result.mirrored)],
        ['逆时针旋转', `${result.turn_degrees}°`], ['标准坐标', vector(result.canonical)]]));
    } catch (error) {
      if (!signal.aborted) failure(target, error);
    } finally {
      if (!signal.aborted) button.disabled = false;
    }
  };
  form.addEventListener('submit', (event) => { event.preventDefault(); drawProbe(); }, {signal});
  drawProbe();
  const filter = q('#coordinate-filter');
  options(filter, [['all', '全部'], ...choices]);
  const draw = () => {
    const rows = data.rows.filter((row) => filter.value === 'all' || row.source === filter.value);
    text('#aligned-total', `${rows.length} 行`);
    table(q('#coordinate-rows'), rows, [
      ['图档', 'source', 'mono'], ['行号', line, 'num'], ['晶圆', 'wafer', 'mono'], ['原点位', original, 'num'],
      ['轴向后', (row) => vector(row.transform.translated), 'num'],
      ['镜像后', (row) => vector(row.transform.mirrored), 'num'], ['旋转 °', (row) => row.transform.turn_degrees, 'num'],
      ['标准点位', (row) => vector(row.transform.canonical), 'num'],
    ]);
  };
  filter.addEventListener('change', draw, {signal});
  draw();
  table(q('#coordinate-issues'), data.issues, issueColumns);
}

function detailLoader(target, signal) {
  let current = 0;
  return async (request, render) => {
    const token = ++current;
    target.replaceChildren(element('p', '正在读取证据…', 'empty'));
    try {
      const result = await request();
      if (!signal.aborted && token === current) render(result);
    } catch (error) {
      if (!signal.aborted && token === current) failure(target, error);
    }
  };
}

async function retest(context) {
  const {api, base, wafer, signal} = context;
  const data = await api(`${base}/retest/${wafer}`);
  const filter = q('#retest-filter');
  const target = q('#retest-detail');
  const load = detailLoader(target, signal);
  const show = (x, y) => load(() => api(`${base}/mask/${wafer}/cell?x=${x}&y=${y}`), (cell) => renderCell(target, cell));
  const draw = () => {
    const rows = data.cells.filter((cell) => filter.value === 'all' || cell.result === filter.value);
    text('#retest-total', `${rows.length} 枚`);
    table(q('#retest-rows'), rows, [
      ['坐标', (cell) => rowButton(vector([cell.x,cell.y]), () => show(cell.x, cell.y))],
      ['裁决', (cell) => status(cell.result)], ['末次', 'attempt', 'num'], ['分档', 'bin', 'num'],
      ['测次链', (cell) => cell.history.map((step) => `T${step.attempt} ${labels[step.result]}`).join(' → ')],
    ]);
    if (rows.length) q('button', q('#retest-rows')).click();
    else load(async () => null, () => target.replaceChildren(element('p', '该状态无芯粒。', 'empty')));
  };
  filter.addEventListener('change', draw, {signal});
  draw();
  table(q('#retest-issues'), data.issues, issueColumns);
}

async function clusters(context) {
  const {api, base, wafer, run, signal} = context;
  const data = await api(`${base}/clusters/${wafer}`);
  const target = q('#cluster-detail');
  const load = detailLoader(target, signal);
  const evidence = q('#cluster-evidence');
  const show = (id) => {
    evidence.replaceChildren(element('p', '正在载入原行…', 'empty'));
    return load(() => api(`${base}/clusters/${wafer}/${id}`).catch((error) => ({error})), (group) => {
      if (group.error) {
        failure(target, group.error);
        evidence.replaceChildren();
        return;
      }
      const graph = element('a', '在阵列查看', 'btn link-btn');
      const params = new URLSearchParams({run: run.run_id, wafer, cluster: id, x: group.anchor[0], y: group.anchor[1]});
      graph.href = `/?${params}`;
      target.replaceChildren(pairs([['簇号', group.id], ['成员', group.size], ['分档', Object.entries(group.bins).map(([bin, qty]) => `${bin} × ${qty}`).join(' · ')],
        ['点位', group.points.map(vector).join(' ')], ['晶圆阵列', graph]]));
      table(evidence, group.rows, [['图档', 'source', 'mono'], ['行号', line, 'num'], ['原点位', original, 'num'],
        ['标准点位', (row) => vector(row.transform.canonical), 'num'], ['测次', (row) => row.measurement.attempt, 'num'],
        ['分档', (row) => row.measurement.bin, 'num']]);
    });
  };
  text('#cluster-total', `${data.length} 簇 · ${data.reduce((sum, group) => sum + group.size, 0)} 枚`);
  table(q('#cluster-rows'), data, [['簇号', (group) => rowButton(group.id, () => show(group.id))], ['成员', 'size', 'num'],
    ['起点', (group) => vector(group.anchor), 'num'], ['包围盒', (group) => `${vector(group.bounds.slice(0,2))} → ${vector(group.bounds.slice(2))}`]]);
  if (data.length) q('button', q('#cluster-rows')).click();
  else for (const box of [target, evidence]) box.replaceChildren(element('p', '此片无最终失败芯粒。', 'empty'));
}

const countNames = {valid: '有效', passed: '通过', failed: '失败', pending: '待测', conflict: '冲突'};
const rowNames = {total: '实收记录', declared_data: '声明数据', accepted: '采信', isolated: '隔离', duplicate: '重复', blank: '空记录', header: '重复档头'};

function auditView({audit, signal}) {
  text('#audit-total', `${audit.wafers.length} 片 · 批良率 ${audit.summary.yield_pct ?? '—'}%`);
  const names = Object.entries(countNames);
  const wa = audit.wafers.flatMap((wafer) => [
    {...wafer, field: '阵列', waferStatus: wafer.balanced ? 'MATCH' : 'UNBALANCED'},
    {...wafer.reference, wafer: wafer.wafer, field: '台账', waferStatus: wafer.status},
  ]);
  table(q('#audit-wafers'), wa, [['晶圆', 'wafer', 'mono'], ['来源', 'field'], ...names.map(([key, name]) => [name,key,'num']),
    ['良率 %', 'yield_pct', 'num'], ['核验', (item) => status(item.waferStatus)]]);
  const differences = audit.wafers.filter((row) => row.status !== 'MATCH' || !row.balanced).map((row) => {
    const values = names.filter(([key]) => row.delta?.[key]).map(([key, name]) => {
      const delta = row.delta[key];
      return `${name} ${delta > 0 ? '+' : ''}${delta}`;
    });
    if (row.missing.length || row.extra.length) values.push(`缺 ${row.missing.join(' ') || '—'} · 多 ${row.extra.join(' ') || '—'}`);
    return [row.wafer, values.join('　') || labels[row.status]];
  });
  if (audit.unknown_reference.length) differences.push(['台账多片', audit.unknown_reference.join('、')]);
  q('#audit-differences').replaceChildren(differences.length ? pairs(differences) : status('MATCH'));
  q('#audit-rows').replaceChildren(status(audit.rows.balanced ? 'MATCH' : 'UNBALANCED'),
    pairs(Object.entries(rowNames).map(([key, name]) => [name, audit.rows[key]])));
  const filter = q('#reason-filter');
  options(filter, [['all', `全部 · ${audit.isolated.length}`], ...Object.entries(audit.reasons).map(([code,count]) => [code, `${code} · ${count}`])]);
  const draw = () => table(q('#audit-issues'), audit.isolated.filter((row) => filter.value === 'all' || row.code === filter.value), issueColumns, '当前图批无隔离行。');
  filter.addEventListener('change', draw, {signal});
  draw();
}

const checkNames = {
  coverage: '参照位覆盖', edge_void: '边缘空位左右镜像', measurement: '测值质量',
};

function missingList(review) {
  const missing = review.checks.coverage.missing;
  if (!missing.length) return element('p', '参照有效位全部有证据。', 'empty');
  const box = element('div', null, 'missing-grid');
  box.append(element('p', `${missing.length} 个格位没有该机台证据：`, 'data-strip'));
  const chips = element('div', null, 'chips');
  for (const point of missing) chips.append(element('span', vector([point.x, point.y]), 'chip mono'));
  box.append(chips);
  return box;
}

function edgeDetail(check) {
  if (check.status === 'UNVERIFIED') {
    return element('p', '该机台在边缘保留带与缺口空位没有任何原始行，无法核查是否整体左右翻。', 'empty');
  }
  const box = element('div', null, 'detail-group');
  if (check.paired.length) {
    box.append(element('p', `${check.paired.length} 组左右成对（或位于 X=0 轴上）：`, 'data-strip'));
    table(box, check.paired.map((item) => ({...item, point: vector([item.x, item.y]),
      mirror: vector([item.mirror_x, item.mirror_y])})), [
      ['格位', 'point', 'mono'], ['分类', (item) => labels[item.code]], ['镜像位', 'mirror', 'mono'],
      ['原行', (item) => item.evidence.map((row) => `${row.source}:${line(row)}`).join(' '), 'mono'],
    ]);
  }
  if (check.unpaired.length) {
    box.append(element('p', `${check.unpaired.length} 个空位找不到同分类的镜像证据：`, 'data-strip'));
    table(box, check.unpaired.map((item) => ({...item, point: vector([item.x, item.y]),
      mirror: vector([item.mirror_x, item.mirror_y])})), [
      ['格位', 'point', 'mono'], ['分类', (item) => labels[item.code]], ['缺失镜像位', 'mirror', 'mono'],
      ['原行', (item) => item.evidence.map((row) => `${row.source}:${line(row)}`).join(' '), 'mono'],
    ]);
  }
  return box;
}

function renderDetail(target, review, stored, onDecide) {
  target.replaceChildren();
  const heading = element('div', null, 'detail-title');
  heading.append(element('strong', `${review.wafer} · ${review.source}`), status(review.verdict));
  target.append(heading);
  target.append(pairs([
    ['覆盖', `${review.checks.coverage.covered} / ${review.checks.coverage.active} 位（${review.checks.coverage.coverage_pct ?? '—'}%）`],
    ['证据哈希', review.evidence_sha256.slice(0, 18) + '…'],
  ]));
  for (const key of review.check_order) {
    const check = review.checks[key];
    const row = element('div', null, 'check-row');
    row.append(element('strong', checkNames[key]), status(check.status));
    target.append(row);
  }
  if (stored) {
    const banner = element('p', null, `stored-banner ${stored.state === 'stale' ? 'is-stale' : 'is-current'}`);
    banner.textContent = stored.state === 'stale'
      ? `旧结论（${labels[stored.verdict]}）引用的参照证据已变化，结论失效，请重算。`
      : `已形成结论：${labels[stored.verdict]} · ${stored.recorded_at} UTC`;
    target.append(banner);
    if (stored.note) target.append(element('p', `备注：${stored.note}`, 'evidence-note'));
  }
  target.append(element('h3', '无证据格位', 'subhead'), missingList(review));
  target.append(element('h3', '边缘空位镜像核查', 'subhead'), edgeDetail(review.checks.edge_void));
  if (review.checks.measurement.issues.length) {
    target.append(element('h3', '测值质量异常', 'subhead'));
    table(target, review.checks.measurement.issues, issueColumns);
  }
  const actions = element('div', null, 'admission-actions');
  const note = element('input', null, 'admission-note');
  note.placeholder = '结论备注（可选）';
  note.maxLength = 200;
  if (stored?.note) note.value = stored.note;
  const button = element('button', stored ? '重算并覆盖结论' : '形成入批结论', 'btn primary');
  button.type = 'button';
  button.addEventListener('click', onDecide(note));
  actions.append(note, button);
  target.append(actions);
}

async function admission({api, base, run, wafer, signal}) {
  const data = await api(`${base}/admission`);
  const reviews = data.reviews;
  const waferReviews = reviews.filter((item) => item.wafer === wafer);
  text('#admission-total', `${reviews.length} 组机台/晶圆 · 当前 ${waferReviews.length} 台`);
  const sourceSelect = q('#admission-source');
  const detail = q('#admission-detail');
  const evidenceBox = q('#admission-evidence');
  const load = detailLoader(detail, signal);
  options(sourceSelect, waferReviews.map((item) => [item.source, item.source]), waferReviews[0]?.source);

  const rowColumns = [
    ['机台图档', 'source', 'mono'], ['晶圆', 'wafer', 'mono'],
    ['结论', (item) => status(item.verdict)],
    ['覆盖', (item) => `${item.checks.coverage.covered}/${item.checks.coverage.active}`, 'num'],
    ['已归档结论', (item) => item.decision
      ? (item.decision.state === 'stale'
        ? element('span', '已失效', 'status fail')
        : status(item.decision.verdict))
      : element('span', '未形成', 'empty')],
  ];

  function reviewUrl(item, action = 'review') {
    const query = new URLSearchParams({wafer: item.wafer, source: item.source});
    return `${base}/admission/${action}?${query}`;
  }

  function showEvidence(current) {
    const merged = current.checks.coverage.evidence
      .concat(current.checks.edge_void.evidence).concat(current.checks.measurement.evidence);
    const ids = new Set();
    table(evidenceBox, merged.filter((row) => !ids.has(row.id) && ids.add(row.id)), [
      ['图档', 'source', 'mono'], ['物理行', line, 'num'], ['晶圆', 'wafer', 'mono'],
      ['机台原始坐标', original, 'num'], ['标准坐标', (row) => vector(row.transform.canonical), 'num'],
      ['记账', (row) => row.code ?? '采信'], ['测次', (row) => row.measurement?.attempt ?? '—', 'num'],
      ['判定', (row) => labels[row.measurement?.result] ?? '—'],
    ], '该机台在本参照晶圆没有可引用的原始行。');
  }

  function show(item) {
    const stateBadge = q('#admission-state');
    const paintState = (decision) => {
      stateBadge.textContent = decision
        ? (decision.state === 'stale' ? '旧结论已失效' : '结论有效') : '尚未形成结论';
      stateBadge.classList.toggle('stale-text', decision?.state === 'stale');
    };
    paintState(item.decision);
    load(() => api(reviewUrl(item)), (review) => {
      paintState(review.decision);
      const decide = (noteInput) => () => load(async () => {
        const reply = await api(`${base}/admission/decisions`, {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({wafer: review.wafer, source: review.source, note: noteInput.value || null}),
        });
        const refreshed = await api(reviewUrl(item));
        return {...refreshed, _created: reply.created, _superseded: reply.superseded};
      }, (refreshed) => {
        paintState(refreshed.decision);
        renderDetail(detail, refreshed, refreshed.decision, decide);
        const index = waferReviews.findIndex((row) => row.source === item.source);
        waferReviews[index] = refreshed;
        table(q('#admission-rows'), waferReviews, rowColumns);
        showEvidence(refreshed);
        feedback(refreshed._created ? '入批结论已形成并归档（每机台每晶圆仅一份）。'
          : refreshed._superseded ? '参照证据已变化，旧结论失效并已按当前证据重算覆盖。'
          : '结论按当前参照证据重算，未新增第二份。');
      });
      renderDetail(detail, review, review.decision, decide);
    });
    showEvidence(item);
  }

  table(q('#admission-rows'), waferReviews, rowColumns);
  sourceSelect.addEventListener('change', () => {
    const current = waferReviews.find((item) => item.source === sourceSelect.value);
    if (current) show(current);
  }, {signal});
  if (waferReviews[0]) show(waferReviews[0]);
}

function runs({run, manifests}) {
  text('#history-total', `${manifests.length} 批`);
  table(q('#history-rows'), manifests, [
    ['运行号', (item) => {
      const link = element('a', item.run_id.slice(0, 12), 'row-link');
      link.href = `/runs?${new URLSearchParams({run: item.run_id})}`;
      if (item.run_id === run.run_id) link.setAttribute('aria-current','true');
      return link;
    }], ['图批', 'lot', 'mono'], ['样例', 'label'], ['状态', (item) => status(item.status)],
    ['生成 UTC', 'created_at', 'mono'],
  ]);
  q('#run-manifest').replaceChildren(pairs([['运行号', run.run_id], ['规则版本', run.rule_version],
    ['计算耗时', `${run.duration_ms} ms`], ['晶圆', run.wafers.join('、')], ['契约 SHA-256', run.contract_sha256], ['结果 SHA-256', run.result_sha256]]));
  table(q('#run-sources'), Object.entries(run.sources).map(([name, value]) => ({name, ...value})), [
    ['图档', 'name', 'mono'], ['字节', 'bytes', 'num'], ['SHA-256', 'sha256', 'mono'],
  ]);
}

export const views = {intake, coordinates, retest, clusters, yield: auditView, admission, runs};
