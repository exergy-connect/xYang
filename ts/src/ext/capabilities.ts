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
