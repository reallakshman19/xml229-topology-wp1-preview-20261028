const ENGINE_URL = new URL('../../converters/xml-cii-2019-standalone/engine.js?v=20261001-single-weight-owners-1', import.meta.url);

export async function runXmlCii2019StandaloneEngineJob(job, runtime = {}) {
  if (typeof runtime.engineRunner === 'function') return runtime.engineRunner(job);
  const engine = await import(ENGINE_URL.href);
  if (typeof engine.runXmlCii2019StandaloneEngine !== 'function') {
    throw new Error('Standalone XML→CII engine module did not export runXmlCii2019StandaloneEngine.');
  }
  return engine.runXmlCii2019StandaloneEngine(job);
}
