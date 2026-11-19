/** Register a tool that validates and displays the topology submitted by an agent. */
export async function registerTopologyTool(modelContext, schema, submit) {
  await modelContext.registerTool({
    name: 'submit_topology',
    description: 'Validate and display a lab.net topology.',
    inputSchema: schema,
    async execute(topology) {
      try {
        const result = await submit(topology);
        return { content: [{ type: 'text', text: JSON.stringify(result) }] };
      } catch (error) {
        return { content: [{ type: 'text', text: String(error?.message ?? error) }], isError: true };
      }
    },
  });
}
