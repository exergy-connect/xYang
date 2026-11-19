import { describe, expect, it } from 'vitest';
import { generateJsonSchema, parseYangString } from '../../src';

const module = parseYangString(`module f { namespace "urn:f"; prefix f;
  feature a; feature b { if-feature a; }
  grouping gated { leaf inherited { type string; } }
  container top {
    leaf always { type string; }
    leaf alpha { if-feature a; mandatory true; type string; }
    leaf beta { if-feature b; type string; }
    leaf not-a { if-feature "not a"; type string; }
    uses gated { if-feature a; }
    container hidden { if-feature a; leaf value { type string; } }
  }
}`);
function properties(features?: Record<string, string[]>) {
  return generateJsonSchema(module, { path: '/f:top', features }).schema.properties as Record<string, unknown>;
}
describe('subtree feature selection', () => {
  it('enables declared features by default and evaluates not', () => {
    expect(Object.keys(properties()).sort()).toEqual(['alpha', 'always', 'beta', 'hidden', 'inherited']);
  });
  it('filters features, inherited uses, and required properties', () => {
    const result = generateJsonSchema(module, { path: '/f:top', features: { f: [] } }).schema;
    expect(Object.keys(result.properties as object).sort()).toEqual(['always', 'not-a']);
    expect(result.required ?? []).not.toContain('alpha');
    expect(() => generateJsonSchema(module, { path: '/f:top/hidden', features: { f: [] } })).toThrow(/not found/);
  });
  it('honors dependencies between features', () => {
    expect(Object.keys(properties({ f: ['b'] })).sort()).toEqual(['always', 'not-a']);
  });
  it('does not change later exports', () => {
    properties({ f: [] });
    expect(properties()).toHaveProperty('alpha');
  });
});

it('removes enumeration values whose feature is disabled', () => {
  const m = parseYangString(`module e { yang-version 1.1; namespace "urn:e"; prefix e; feature f;
    typedef mode { type enumeration { enum basic; enum advanced { if-feature f; } } }
    container top { leaf mode { type mode; } }
  }`);
  const enabled = generateJsonSchema(m, { path: '/e:top' }).schema;
  const disabled = generateJsonSchema(m, { path: '/e:top', features: { e: [] } }).schema;
  expect((enabled.$defs as Record<string, { enum: string[] }>).mode.enum).toEqual(['basic', 'advanced']);
  expect((disabled.$defs as Record<string, { enum: string[] }>).mode.enum).toEqual(['basic']);
});

it('removes disabled choice branches', () => {
  const m = parseYangString(`module c { namespace "urn:c"; prefix c; feature f;
    container top { choice selection { case gated { if-feature f; leaf a { type string; } } case open { leaf b { type string; } } } }
  }`);
  const s = generateJsonSchema(m, { path: '/c:top', features: { c: [] } }).schema;
  expect(JSON.stringify(s)).not.toContain('"a"');
  expect(JSON.stringify(s)).toContain('"b"');
});

it('removes leafrefs to feature-disabled nodes while keeping the value type', () => {
  const m = parseYangString(`module r { namespace "urn:r"; prefix r; feature f;
    container top { leaf target { if-feature f; type uint32; } leaf ref { type leafref { path "../target"; } } }
  }`);
  const result = generateJsonSchema(m, { path: '/r:top', features: { r: [] } });
  const ref = (result.schema.properties as any).ref;
  expect(ref.type).toBe('integer');
  expect(ref['x-yang'].path).toBeUndefined();
  expect(result.diagnostics[0].reason).toContain('disabled');
});

it('fails loudly when an imported grouping loses feature context', async () => {
  const { mkdtempSync, writeFileSync, rmSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const { join } = await import('node:path');
  const { parseYangFile } = await import('../../src');
  const dir = mkdtempSync(join(tmpdir(), 'xyang-features-'));
  try {
    writeFileSync(join(dir, 'lib.yang'), 'module lib { namespace "urn:lib"; prefix l; feature f; grouping g { leaf x { if-feature f; type string; } } }');
    writeFileSync(join(dir, 'main.yang'), 'module main { namespace "urn:main"; prefix m; import lib { prefix l; } container top { uses l:g; } }');
    const module = parseYangFile(join(dir, 'main.yang'));
    expect(() => generateJsonSchema(module, {path: '/m:top'})).toThrow(/unqualified if-feature/);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

it('reports a shared leafref once across choice branches', () => {
  const m = parseYangString(`module c { namespace "urn:c"; prefix c; feature f;
    container top { leaf target { if-feature f; type uint32; }
      leaf ref { type leafref { path "../target"; } }
      choice selection { case gated { if-feature f; leaf a { type string; } } case open { leaf b { type string; } } }
    }
  }`);
  const result = generateJsonSchema(m, { path: '/c:top', features: { c: [] } });
  expect(result.diagnostics).toHaveLength(1);
  expect(result.diagnostics[0].reason).toBe('target is disabled by feature selection');
});
