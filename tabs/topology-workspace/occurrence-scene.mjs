/** Read-only occurrence scene. Authority remains PSI116 analysis/transaction. */
const local = element => (element?.localName || element?.nodeName || '').replace(/^.*:/, '');
const children = (element, name) => [...(element?.children || [])].filter(child => local(child) === name);
const child = (element, name) => children(element, name)[0]?.textContent?.trim() || '';
function coordinate(value) {
  const pieces = value.trim().split(/\s+/);
  if (pieces.length !== 3 || pieces.some(v => v === '' || !Number.isFinite(Number(v)))) return null;
  const [x, y, z] = pieces.map(Number);
  return { x, y, z };
}
const integer = value => /^-?\d+$/.test(value) ? Number(value) : null;
const escapeValue = value => String(value ?? '').replace(/[&<>"']/g,
  ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
export { escapeValue };

export function parseOccurrenceScene(xmlText, sourceSha256, Parser = globalThis.DOMParser) {
  if (typeof Parser !== 'function') throw Error('XML DOM parser unavailable');
  const doc = new Parser().parseFromString(xmlText, 'application/xml');
  if (doc.querySelector('parsererror')) throw Error('Malformed XML source');
  const all = [...doc.getElementsByTagName('*')];
  const branches = (all.length ? all : [...doc.getElementsByTagName('Branch')])
    .filter(el => local(el) === 'Branch');
  if (!branches.length) throw Error('Expected PSI116 <Branch>/<Node> XML');
  const records = [], segments = [], branchList = [];
  branches.forEach((branch, branchIndex) => {
    const name = child(branch, 'Branchname') || 'Branch ' + (branchIndex + 1);
    const b = { name, index: branchIndex, ordinal: branchIndex + 1, count: 0 };
    let routePrevious = null;
    children(branch, 'Node').forEach((node, sourceIndex) => {
      const label = child(node, 'NodeNumber'), number = integer(label);
      const type = child(node, 'ComponentType').toUpperCase();
      const nodeName = child(node, 'NodeName'), refNo = child(node, 'ComponentRefNo');
      const support = type === 'ATTA' && /\/SREF/i.test(nodeName);
      const position = coordinate(child(node, 'Position'));
      const key = 'B' + branchIndex + ':N' + (number === null ? 'none' : number) + ':S' + sourceIndex;
      const route = !!position && number !== null && number > 0 && type !== 'GASK' && !support;
      const record = {
        id: sourceSha256 + ':' + key, key, branchIndex, sourceIndex,
        branchOrdinal: branchIndex + 1, nodeOrdinal: sourceIndex + 1, branchName: name,
        nodeNumber: number, nodeNumberRaw: label, nodeName, type, refNo,
        endpoint: child(node, 'Endpoint'), connectionType: child(node, 'ConnectionType'),
        position, route, support, restraint: children(node, 'Restraint').length > 0,
        weight: child(node, 'Weight'), xmlFragment: new XMLSerializer().serializeToString(node),
      };
      records.push(record);
      if (route && routePrevious) segments.push({ a: routePrevious.id, b: record.id, branchIndex });
      if (route) routePrevious = record;
      b.count++;
    });
    branchList.push(b);
  });
  const located = records.filter(record => record.position);
  const axes = ['x', 'y', 'z'];
  const min = Object.fromEntries(axes.map(a => [a, located.reduce((v,r) => Math.min(v,r.position[a]),Infinity)]));
  const max = Object.fromEntries(axes.map(a => [a, located.reduce((v,r) => Math.max(v,r.position[a]),-Infinity)]));
  const center = Object.fromEntries(axes.map(a => [a, located.length ? (min[a] + max[a]) / 2 : 0]));
  const span = located.length ? Math.max(1, ...axes.map(a => max[a] - min[a])) : 1;
  return { sourceSha256, records, segments, branches: branchList,
    bounds: { min, max, center, span }, byId: new Map(records.map(r => [r.id, r])),
    byKey: new Map(records.map(r => [r.key, r])) };
}

/** Use PSI116 findings' original node_keys, not node numbers, for authoritative highlighting. */
export function affectedOccurrenceIds(action, findings, scene) {
  const findingIds = new Set(action?.finding_ids || []);
  const keys = new Set(findings.filter(f => findingIds.has(f.finding_id))
    .flatMap(f => f.node_keys || []));
  return [...keys].map(key => scene.byKey.get(key)?.id).filter(Boolean);
}
