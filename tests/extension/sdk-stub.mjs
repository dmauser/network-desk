// Test double for "@github/copilot-sdk/extension": captures the joinSession
// config so tests can drive tool handlers and hooks without the CLI host.
export async function joinSession(config) {
    const logs = [];
    globalThis.__networkDeskSession = { config, logs };
    return {
        log: async (msg, opts) => { logs.push({ msg, opts }); },
    };
}
