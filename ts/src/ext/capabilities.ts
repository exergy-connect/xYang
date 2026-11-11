import type { YangModule, YangStatement } from "../core/model";

export type ExtensionCapability = {
  id: string;
  description?: string;
};

const capabilities = new Map<string, ExtensionCapability>();

export function registerCapability(capability: ExtensionCapability): void {
  capabilities.set(capability.id, capability);
}

export function getCapability(id: string): ExtensionCapability | undefined {
  return capabilities.get(id);
}

/** Marker that an extension is applied at parse time. Export fails unless the JSON form supports it. */
export type ExtensionApplyCallback = (
  invocation: YangStatement,
  contextModule: YangModule
) => YangStatement | undefined;

const callbacks = new Map<string, ExtensionApplyCallback>();

function key(moduleName: string, extensionName: string): string {
  return `${moduleName}:${extensionName}`;
}

export function registerExtensionApplyCallback(
  moduleName: string,
  extensionName: string,
  callback: ExtensionApplyCallback
): void {
  callbacks.set(key(moduleName, extensionName), callback);
}

export function getExtensionApplyCallback(
  moduleName: string,
  extensionName: string
): ExtensionApplyCallback | undefined {
  return callbacks.get(key(moduleName, extensionName));
}

let loaded = false;

/** RFC 8791 is applied by {@link applyBuiltinExtensionInvocations}. The marker only records that it has a callback. */
export function ensureBuiltinExtensionsLoaded(): void {
  if (loaded) {
    return;
  }
  loaded = true;
  const marker: ExtensionApplyCallback = (invocation) => invocation;
  registerExtensionApplyCallback("ietf-yang-structure-ext", "structure", marker);
  registerExtensionApplyCallback("ietf-yang-structure-ext", "augment-structure", marker);
}
