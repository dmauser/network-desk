// Node module-resolution hook: redirect the Copilot SDK import to the local stub.
const STUB = new URL("./sdk-stub.mjs", import.meta.url).href;

export async function resolve(specifier, context, nextResolve) {
    if (specifier === "@github/copilot-sdk/extension") {
        return { url: STUB, shortCircuit: true };
    }
    return nextResolve(specifier, context);
}
