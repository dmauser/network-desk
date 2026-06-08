# Configuring the GCP documentation MCP (Developer Knowledge MCP)

This guide explains how to configure the **GCP** documentation MCP server that Network Desk uses for [validation-first fact-checking](../README.md#validation-first-per-cloud-documentation-mcp), matching how `microsoft-learn` (Azure) and `aws-docs` (AWS) are configured.

Google's [Developer Knowledge MCP](https://developers.google.com/knowledge/mcp) server (`developerknowledge.googleapis.com`) is the GCP equivalent of Microsoft Learn (Azure) and AWS Documentation (AWS). It exposes read-only tools — `search_documents`, `get_documents`, and `answer_query` — over Google's official corpus (`docs.cloud.google.com`, Firebase, Android, Maps, and more). It is **public preview**, **English-only**, and **analysis-only safe**: it has no mutating tools.

Register it under the **exact name `gcp-docs`** — that is the identifier Network Desk looks for. Until a server named `gcp-docs` is present, GCP answers run in ⚠️ **unverified** mode.

> ⚠️ **Do not use `networkmanagement.googleapis.com/mcp` for validation.** That is an *operational* API (create/get/list/delete **Connectivity Tests**) that mutates live resources — the wrong tool for documentation fact-checking. For validation-first use, only the Developer Knowledge MCP (`developerknowledge.googleapis.com`) is appropriate.

## Setup

```bash
# 1. Enable the API
gcloud services enable developerknowledge.googleapis.com --project=PROJECT_ID

# 2. Enable the MCP server
gcloud beta services mcp enable developerknowledge.googleapis.com --project=PROJECT_ID

# 3. Create an API key, then restrict it to this service
gcloud services api-keys create --display-name="Network Desk gcp-docs"
gcloud services api-keys update KEY_NAME \
  --api-target=service=developerknowledge.googleapis.com
```

Register it with Copilot CLI via the `/mcp add` wizard — **Name** `gcp-docs`, **type** `HTTP`, **URL** `https://developerknowledge.googleapis.com/mcp`, **header** `X-goog-api-key: YOUR_API_KEY` — or use the one-line command:

```bash
copilot mcp add --transport http gcp-docs https://developerknowledge.googleapis.com/mcp --header "X-goog-api-key: YOUR_API_KEY"
```

…or drop in the JSON config block:

```json
{
  "mcpServers": {
    "gcp-docs": {
      "type": "http",
      "url": "https://developerknowledge.googleapis.com/mcp",
      "headers": { "X-goog-api-key": "YOUR_API_KEY" }
    }
  }
}
```

> ⚠️ **Auth gotcha — use the `X-goog-api-key` header.** The API key must be passed in the **`X-goog-api-key`** request header — **not** as an `Authorization: Bearer <key>` header and **not** as a `?key=` query parameter. If the server returns **`401 "missing OAuth2 credential"`**, you are almost certainly using `Authorization: Bearer` (or no header) instead of `X-goog-api-key`; switch to the `X-goog-api-key` header and restart the CLI. A correctly-authenticated `initialize` call returns `HTTP/1.1 200 OK`.

## Verify

```bash
/mcp list   # gcp-docs should be listed and connected
```

Then ask a test question such as *"How do I list Cloud Storage buckets?"* — you should see the model invoke the `search_documents` tool against `gcp-docs`.

## OAuth / ADC alternative (no API key)

If you would rather not manage an API key, authenticate with Application Default Credentials and let the server use your Google identity:

```bash
gcloud auth application-default login
```

…then register `gcp-docs` with `"authProviderType": "google_credentials"` instead of the `X-goog-api-key` header.

> **Tip:** Keep prompts specific (name the product and the exact task) to avoid pulling large documentation pages and bloating token usage. Source: Google's official [Developer Knowledge MCP docs](https://developers.google.com/knowledge/mcp).
