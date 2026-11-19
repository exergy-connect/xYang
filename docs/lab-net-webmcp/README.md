# lab.net WebMCP topology submission

This example derives a WebMCP tool's input schema from `lab-net.yang` at page
load. The `submit_topology` tool validates the agent's native JSON topology
with xYang and displays the submitted JSON on the page. Invalid submissions
return validation errors and leave the last valid submission visible.

The browser-ready files and a copy of the YANG model are included here. Serve
the repository over HTTP, for example:

```sh
cd xYang
python -m http.server 8765
```

Open `http://localhost:8765/docs/lab-net-webmcp/` in a WebMCP-enabled browser.
Ask an agent to call `submit_topology` with a native JSON object, for example
`{"nodes":{"r1":{}}}`. The page displays the number of constraints omitted
from the subtree schema; the complete model is used for validation before a
submission is displayed.

If the page says “This browser does not expose WebMCP,” enable it in Chrome:

1. Open `chrome://flags/#enable-webmcp-testing` in the address bar.
2. Set the flag to **Enabled** and relaunch Chrome.
3. Return to the example and reload the page.

If the flag is unavailable, update Chrome and try again. See
[Chrome's WebMCP instructions](https://developer.chrome.com/docs/ai/webmcp/)
for current availability.

To rebuild the browser bundle after changing the example or xYang, install the
TypeScript dependencies and run `node docs/lab-net-webmcp/build.mjs` from the
repository root. To also refresh the model copy from a lab.net checkout, pass
its path: `node docs/lab-net-webmcp/build.mjs ../lab.net`.

WebMCP is an evolving browser API; see the
[WebMCP specification](https://webmachinelearning.github.io/webmcp/).

To smoke-test without a browser agent, serve the parent directory of adjacent
`xYang` and `lab.net` checkouts on port 8765 and run
`CHROME_PATH=/path/to/chrome node docs/lab-net-webmcp/smoke.cjs ../lab.net`
from the xYang directory. This mocks WebMCP registration and checks that valid
agent input is displayed unchanged and invalid input is rejected in Chromium.
