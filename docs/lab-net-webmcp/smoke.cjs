// Run after building the example and starting the HTTP server described in README.md.
const { createRequire } = require('node:module');
const { resolve } = require('node:path');
const lab = resolve(process.argv[2] ?? '../lab.net');
const requireLab = createRequire(resolve(lab, 'package.json'));
const { chromium } = requireLab('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || undefined });
  try {
    const page = await browser.newPage();
    await page.addInitScript(() => Object.defineProperty(document, 'modelContext', {
      configurable: true, value: { async registerTool(tool) { window.registeredTool = tool; } }
    }));
    await page.goto('http://localhost:8765/xYang/docs/lab-net-webmcp/');
    await page.waitForFunction(() => window.registeredTool || document.querySelector('#status').textContent.startsWith('Could not'));
    const result = await page.evaluate(async () => {
      if (!window.registeredTool) throw new Error(document.querySelector('#status').textContent);
      const topology = { name: 'agent-lab', nodes: { r1: {}, r2: {} } };
      const valid = await window.registeredTool.execute(topology);
      const displayed = JSON.parse(document.querySelector('#topology-output').textContent);
      const invalid = await window.registeredTool.execute({ nodes: {} });
      return { name: window.registeredTool.name, topology, displayed, valid, invalid,
        afterInvalid: JSON.parse(document.querySelector('#topology-output').textContent) };
    });
    if (result.name !== 'submit_topology' || result.valid.isError || !result.invalid.isError ||
        JSON.stringify(result.topology) !== JSON.stringify(result.displayed) ||
        JSON.stringify(result.displayed) !== JSON.stringify(result.afterInvalid)) throw new Error(JSON.stringify(result));
    console.log('Agent submission displayed unchanged; invalid submission rejected.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
