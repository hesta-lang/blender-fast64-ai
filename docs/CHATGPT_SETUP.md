# ChatGPT setup

## Current limitation

A custom remote MCP server with write access cannot be connected from the ChatGPT mobile app. Availability depends on the ChatGPT plan and workspace configuration; check the current OpenAI Help Center before deployment. Do not assume a Free account can add a custom MCP server.

## Local development

Run the server with `python -m server.main`. It uses stdio and is intended for local MCP clients, not direct ChatGPT mobile access.

## Remote connection (future)

Before exposing this service, add HTTPS and a standards-compliant OAuth 2.1 authorization server/resource-server flow with PKCE, issuer/audience validation, scoped access tokens and per-user project isolation. The current repository version is a local alpha and must not be exposed publicly.

## Using Blender files

Place source models in `data/workspace/imports/`. Call `import_model(filename="Steve.fbx")` from an MCP client. Back up the .blend file before testing any modification. Use `fast64_export_operators` to discover actual installed export operators; never assume a particular operator exists.
