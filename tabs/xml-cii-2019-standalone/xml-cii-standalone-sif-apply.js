// Writes SIF / Tee-type / node-ownership facts collected in the preview/resolver tabs into the
// enriched XML or InputXML text so the CII converter picks them up as first-class data instead of
// the facts only being visible in the standalone preview UI.
const SIF_NODE_FIELDS = Object.freeze(['TEEDESC_REFBASIS', 'TEEDESC_POS', 'TEEDESC', 'DTXR_POS', 'DTXR_PS', 'DTXR']);

function text(value) { return value === undefined || value === null ? '' : String(value); }
function localName(node) { return text(node?.localName || node?.nodeName).replace(/^.*:/, ''); }

function findChildren(root, name) {
  const out = [];
  const wanted = name.toUpperCase();
  const visit = (node) => { for (const child of Array.from(node.children || [])) { if (localName(child).toUpperCase() === wanted) out.push(child); visit(child); } };
  visit(root);
  return out;
}

function findChild(element, name) {
  return Array.from(element.children || []).find((child) => localName(child) === name) || null;
}

function setChildText(doc, element, name, value) {
  const existing = findChild(element, name);
  const child = existing || doc.createElement(name);
  child.textContent = text(value);
  if (!existing) element.appendChild(child);
}

function parseXmlDocument(sourceText) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(text(sourceText), 'application/xml');
  const parseError = doc.querySelector && doc.querySelector('parsererror');
  if (parseError) throw new Error(parseError.textContent || 'SIF apply: source XML parse failed.');
  return doc;
}

function sifFieldsFromFact(fact) {
  const out = {};
  if (fact.teeDescription) out.TEEDESC = fact.teeDescription;
  if (fact.teeDescriptionRefBasis) out.TEEDESC_REFBASIS = fact.teeDescriptionRefBasis;
  if (fact.teeDescriptionPos) out.TEEDESC_POS = fact.teeDescriptionPos;
  if (fact.dtxr) out.DTXR = fact.dtxr;
  if (fact.dtxrPos) out.DTXR_POS = fact.dtxrPos;
  if (fact.dtxrPs) out.DTXR_PS = fact.dtxrPs;
  return out;
}

// PSI/enriched XML: xml_to_cii2019_direction.py's _tee_description_by_node() reads TEEDESC_REFBASIS /
// TEEDESC_POS / TEEDESC / DTXR_POS / DTXR_PS / DTXR child text off <Node NodeNumber="N"> records.
// Writing the same field names here means no python change is required to pick these facts up.
function applySifFactsToXml(sourceText, sifFacts) {
  const doc = parseXmlDocument(sourceText);
  const nodesByNumber = new Map();
  for (const node of findChildren(doc.documentElement, 'Node')) {
    const numberChild = findChild(node, 'NodeNumber');
    const number = numberChild ? Number(text(numberChild.textContent).trim()) : NaN;
    if (Number.isFinite(number)) nodesByNumber.set(number, node);
  }
  let applied = 0;
  let skipped = 0;
  const missingOwnerNode = [];
  for (const fact of sifFacts) {
    const ownerNode = Number(fact?.nodeNumber ?? fact?.ownerNode ?? fact?.node);
    const fields = sifFieldsFromFact(fact || {});
    if (!Number.isFinite(ownerNode) || !Object.keys(fields).length) { skipped += 1; continue; }
    const node = nodesByNumber.get(ownerNode);
    if (!node) { missingOwnerNode.push(ownerNode); continue; }
    for (const [name, value] of Object.entries(fields)) setChildText(doc, node, name, value);
    applied += 1;
  }
  const serializer = new XMLSerializer();
  return { text: serializer.serializeToString(doc), diagnostics: { applied, skipped, missingOwnerNode } };
}

function normalizeNode(value) { const raw = text(value).trim(); const n = Number(raw); return Number.isFinite(n) ? String(Math.round(n)) : raw; }

// InputXML: write the same DTXR_POS/DTXR_PS side-load-style fields onto the owning PIPINGELEMENT
// (matched by FROM_NODE->TO_NODE, or the TO_NODE alone when only a node number is supplied), plus a
// TeeSifType hint mirroring defaultTeeSifType so the standalone/CAESAR field convention stays intact.
function applySifFactsToInputXml(sourceText, sifFacts) {
  const doc = parseXmlDocument(sourceText);
  const elements = findChildren(doc.documentElement, 'PIPINGELEMENT');
  const byKey = new Map();
  const byToNode = new Map();
  for (const element of elements) {
    const from = normalizeNode(element.getAttribute('FROM_NODE'));
    const to = normalizeNode(element.getAttribute('TO_NODE'));
    byKey.set(`${from}->${to}`, element);
    if (to) byToNode.set(to, element);
  }
  let applied = 0;
  let skipped = 0;
  const missingOwnerNode = [];
  for (const fact of sifFacts) {
    const key = fact?.nodeKey ? text(fact.nodeKey).trim() : '';
    const ownerNode = fact?.ownerNode != null ? normalizeNode(fact.ownerNode) : (fact?.nodeNumber != null ? normalizeNode(fact.nodeNumber) : '');
    const fields = sifFieldsFromFact(fact || {});
    if (fact?.teeSifType != null) fields.TeeSifType = fact.teeSifType;
    if ((!key && !ownerNode) || !Object.keys(fields).length) { skipped += 1; continue; }
    const element = (key && byKey.get(key)) || (ownerNode && byToNode.get(ownerNode));
    if (!element) { missingOwnerNode.push(key || ownerNode); continue; }
    for (const [name, value] of Object.entries(fields)) setChildText(doc, element, name, value);
    applied += 1;
  }
  const serializer = new XMLSerializer();
  return { text: serializer.serializeToString(doc), diagnostics: { applied, skipped, missingOwnerNode } };
}

export function applyStandaloneSifFacts(sourceText, sourceKind, sifFacts) {
  const facts = Array.isArray(sifFacts) ? sifFacts.filter((fact) => fact && typeof fact === 'object') : [];
  if (!facts.length) return { text: text(sourceText), diagnostics: { applied: 0, skipped: 0, missingOwnerNode: [] } };
  try {
    return sourceKind === 'inputxml' ? applySifFactsToInputXml(sourceText, facts) : applySifFactsToXml(sourceText, facts);
  } catch (error) {
    return { text: text(sourceText), diagnostics: { applied: 0, skipped: facts.length, missingOwnerNode: [], error: error?.message || String(error) } };
  }
}

export { SIF_NODE_FIELDS };
