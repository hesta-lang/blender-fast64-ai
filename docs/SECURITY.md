# Security notes

This is an early local-development alpha. It is not safe to expose to the public Internet.

- No arbitrary Python, shell, or filesystem tool is exposed to the model.
- The worker accepts a fixed set of actions and validates object names, geometry, bones, skin weights, material values, filenames and export operator properties.
- Imported model and texture files are restricted to workspace import folders; export path properties are restricted to \`workspace/exports/\`.
- Fast64 execution is limited to operator identifiers discovered from the currently registered Blender operators. This is not a security sandbox for the Fast64 addon itself.
- Blender parses complex third-party file formats and addons. Run it with an unprivileged account in an isolated container, with no sensitive host mounts.
- Use backups before modifying \`.blend\` files or invoking Fast64 exporters. Fast64 may modify project files and may crash on some material operations.
- Do not expose stdio or a development HTTP server to the public Internet.
- A future remote deployment must implement HTTPS, OAuth 2.1, per-user authorization, tenant isolation, rate limits, upload quarantine and audit logging.
- Operator discovery is not proof that an export will work. Some Fast64 operators need UI context, configured projects, F3D materials, or other scene-specific state.
