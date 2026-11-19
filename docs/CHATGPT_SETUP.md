# ChatGPT setup

## Current limitation

This repository is a local MCP stdio server. It is not an Internet service and is not automatically connected to this ChatGPT conversation. A custom remote MCP server requires a supported ChatGPT plan and client surface; the ChatGPT mobile app does not provide a place to configure a custom MCP server. Do not publish this alpha as a public endpoint.

## Local development

Run the server with \`python -m server.main\` from the repository root. Configure a local MCP-compatible client to start that command using Python 3.11 and the repository as its working directory. The server launches Blender in background mode for each operation; set \`BLENDER_BIN\` if the Blender executable is not named \`blender\`.

## Blender workspace

- Place model files in \`data/workspace/imports/\` before calling \`import_model\`.
- Place image textures in the same folder before calling \`create_material(texture_filename=...)\`.
- \`create_mesh_object\` creates editable geometry from vertex coordinates and face indices.
- \`create_armature\` builds the bone hierarchy; \`bind_mesh_to_armature\` tries Blender automatic weights, and \`set_vertex_weights\` accepts explicit per-vertex weights.
- Use \`smart_uv_unwrap\` to generate a UV map. Review seams/islands before production use.
- Exports are restricted to \`data/workspace/exports/\`. Use \`fast64_export_operators\` to inspect the installed Fast64 version, then pass one exact returned operator identifier to \`fast64_run_export\`.

Back up the \`.blend\` project and the target game repository before testing edits or exports. Fast64 operators may require a configured decomp project, F3D materials, selection, or a UI context that is unavailable in background mode.

## Remote connection (future)

Before exposing this service, add HTTPS and a standards-compliant OAuth 2.1 authorization/resource-server flow with PKCE, issuer/audience validation, scoped access tokens, per-user project isolation, rate limits, upload quarantine and audit logging. The current repository version is a local alpha and must not be exposed publicly.
