function text(value) { return value === undefined || value === null ? '' : String(value); }
function safeName(name) { return (text(name).trim() || 'input.xml').replace(/[\\/:*?"|]/g, '_'); }
export function outputStem(sourceName) { const name = safeName(sourceName); const idx = name.lastIndexOf('.'); return idx > 0 ? name.slice(0, idx) : name; }
function parseObject(raw) { try { const v = JSON.parse(text(raw) || '{}'); return v && typeof v === 'object' && !Array.isArray(v) ? v : {}; } catch { return {}; } }
function boolOrNull(value) { if (value === true || value === false) return value; if (value === undefined || value === null || value === '') return null; const t = text(value).toLowerCase(); if (['1','true','yes','on'].includes(t)) return true; if (['0','false','no','off'].includes(t)) return false; return null; }
function pushText(argv, flag, value) { const v = text(value).trim(); if (v) argv.push(flag, v); }

export function buildStandaloneCiiInvocation(job, paths, jobDir) {
  const sourceKind = job.sourceKind === 'inputxml' ? 'inputxml' : 'xml';
  const options = job.options || {};
  const stem = outputStem(job.sourceName);
  const outputName = sourceKind === 'inputxml' ? `${stem}_inputxml_to_cii2019.cii` : `${stem}_xml_to_cii2019_standalone.cii`;
  const outputPath = `${jobDir}/${outputName}`;
  if (sourceKind === 'inputxml') {
    return { scriptPath: '/scripts/inputxml_to_cii2019.py', outputPath, outputName, argv: ['/scripts/inputxml_to_cii2019.py', '--input', paths.inputPath, '--output', outputPath] };
  }
  const cfg = parseObject(job.supportConfigJson);
  const split = boolOrNull(options.splitCondensedValveFlange) ?? boolOrNull(cfg.splitCondensedValveFlange) ?? boolOrNull(cfg.split_condensed_valve_flange);
  const mode = ['all', 'none'].includes(text(options.coordsMode).toLowerCase()) ? text(options.coordsMode).toLowerCase() : 'first';
  const argv = ['/scripts/xml_to_cii2019_runtime_custody.py', '--input', paths.inputPath, '--output', outputPath, '--coords-mode', mode];
  if (options.kgToNewton !== false) argv.push('--weight-scale', '10');
  pushText(argv, '--support-config-json', job.supportConfigJson);
  if (split === true) argv.push('--split-condensed-valve-flange');
  else if (split === false) argv.push('--no-split-condensed-valve-flange');
  if (paths.stagedJsonPath) argv.push('--staged-json', paths.stagedJsonPath);
  if (paths.xml229NativeFinalPacketPath) {
    if (!paths.xml229NativeMassProofPath) throw new Error('XML229_NATIVE_PROOF_PATH_REQUIRED');
    if (options.kgToNewton === false) throw new Error('XML229_NATIVE_FORCE_UNIT_REQUIRED');
    argv.push('--xml229-native-final-packet', paths.xml229NativeFinalPacketPath,
      '--xml229-native-mass-proof', paths.xml229NativeMassProofPath);
  }
  if (options.useRestraintTypeBasedOnJson === false) argv.push('--no-use-restraint-type-based-on-json');
  else argv.push('--use-restraint-type-based-on-json');
  return { scriptPath: '/scripts/xml_to_cii2019_runtime_custody.py', outputPath, outputName, argv };
}
