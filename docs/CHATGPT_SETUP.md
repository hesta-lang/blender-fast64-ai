# ChatGPT setup

## Supported connection modes

This project currently exposes a local MCP server over standard input/output (stdio). That is appropriate for a local MCP client on the same computer as Blender. It is not a public endpoint and cannot be reached by this ChatGPT conversation directly.

According to the current OpenAI Help Center guidance, custom MCP apps are configured from ChatGPT on the web, not the mobile app. Full custom MCP/write support is available to Business and Enterprise/Edu workspaces; Pro has read/fetch-only custom MCP support. Free is not listed as a supported plan for custom MCP connections. The account currently used for this project is Free on Android, so a direct live MCP connection is not available in that setup.

Official guidance: https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt

## Recommended workflow for Android

The repository includes a GitHub Actions path that does not require Blender to be installed on the phone:

1. Upload a trusted .blend file under inbox/ in the GitHub repository.
2. Open Actions → Blender Project Diagnostics → Run workflow.
3. Set blend_path to the complete relative file path, such as inbox/Steve.blend.
4. Download the blender-pipeline-report artifact.
5. Upload pipeline-report.json into the ChatGPT conversation. The report includes the SHA-256 hash of the exact source file so we can distinguish revisions.

Keep relative texture folders and other assets beside the .blend file. The diagnostic copies those sibling files into a temporary worker directory. It will report missing external references rather than silently repairing them. The workflow does not save or modify the uploaded .blend.

## Local Blender + MCP client

Run the server with python -m server.main from the repository root. Configure a compatible local MCP client to start that command using Python 3.11 and the repository as its working directory. The server launches Blender in background mode for each operation. Set BLENDER_BIN if the Blender executable is not named blender.

Each worker loads data/workspace/active.blend when it exists. Successful scene mutations save the project automatically, preserving an active.blend1 backup. inspect_asset_pipeline is read-only and traces the active project from mesh and UV data through materials, image nodes, armature modifiers, bones and vertex groups.

For Fast64, set BFAI_FAST64_ADDON_PATH to the directory containing the addon's __init__.py, or enable the addon in the Blender profile used by the worker. Run convert_materials_to_f3d before exporting; an ordinary Principled BSDF material is not a native F3D material. export_sm64_armature writes Fast64 C geolayout output and a bfai_export_manifest.json with source metadata and output hashes. It does not create a DynOS pack.

## Future remote MCP connection

A direct ChatGPT connection requires a reachable remote MCP endpoint over HTTPS or an approved secure tunnel, with OAuth 2.1 authorization, scoped access tokens, issuer/audience validation, per-user project isolation, rate limits, upload quarantine and audit logging. The current local stdio server does not implement these services. Do not expose it publicly or create an unauthenticated HTTP tunnel.

Even after that remote service is built, the user's current Free/mobile setup would still not be able to add a custom MCP app. The GitHub Actions report workflow is therefore the practical supported path for this project at present.
