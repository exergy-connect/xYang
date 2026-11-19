import { parseYangString, generateJsonSchema, YangValidator } from 'xyang';
import { registerTopologyTool } from './tool.js';

const $ = selector => document.querySelector(selector);
const status = $('#status');

$('#copy-webmcp-flag').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText($('#webmcp-flag').textContent);
    $('#copy-status').textContent = 'Copied.';
  } catch {
    $('#copy-status').textContent = 'Select and copy the address above.';
  }
});

try {
  const response = await fetch('./lab-net.yang');
  if (!response.ok) throw new Error(`Could not load lab-net.yang: ${response.status}`);
  const module = parseYangString(await response.text());
  const { schema, diagnostics } = generateJsonSchema(module, { path: '/lab:topology', nativeJson: true });
  $('#schema-output').textContent = JSON.stringify(schema, null, 2);
  const validator = new YangValidator(module);
  const submit = topology => {
    const validation = validator.validateDetailed({ topology }, { nativeJson: true });
    if (!validation.valid) throw new Error(validation.errors.map(error => `${error.path || '/'}: ${error.message}`).join('\n'));
    $('#topology-output').textContent = JSON.stringify(topology, null, 2);
    $('#empty').hidden = true;
    $('#topology-output').hidden = false;
    $('#submission-state').textContent = 'VALIDATED';
    return { valid: true, warnings: validation.warnings };
  };
  if (document.modelContext) {
    await registerTopologyTool(document.modelContext, schema, submit);
    $('#connection-label').textContent = 'WebMCP connected';
    status.textContent = `Tool registered · ${diagnostics.length} out-of-scope constraints omitted`;
  } else {
    $('#webmcp-help').hidden = false;
    $('.top-meta .live-dot').classList.add('off');
    $('#connection-label').textContent = 'WebMCP unavailable';
    status.textContent = 'This browser does not expose WebMCP.';
  }
} catch (error) {
  $('.top-meta .live-dot').classList.add('off');
  $('#connection-label').textContent = 'Setup incomplete';
  status.textContent = `Could not set up the example: ${error.message}`;
}
