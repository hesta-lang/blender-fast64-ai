# Security notes

This is an early local-development alpha. It is not safe to expose to the public Internet.

- No arbitrary Python, shell, or filesystem tool is exposed to the model.
- The worker accepts a fixed set of actions and validates object names, geometry, bones, material values, filenames and export operator properties.
- SM64 binary skinning validates exactly one deform-bone assignment per vertex and writes a weight of 1.0.
- Imported model and texture files are restricted to workspace import folders; export folder parameters and Fast64 file/directory properties are restricted to `workspace/exports/`. Imported objects receive source filename and SHA-256 provenance tags.
- Each Blender worker process loads the persisted `active.blend`; successful scene mutations save it automatically. Blender keeps a `.blend1` backup.
- Fast64 execution is limited to known integration actions or operator identifiers discovered from the currently registered Blender operators. This is not a security sandbox for the Fast64 addon itself.
- Fast64 is third-party code and can modify files or crash Blender. Run it in an isolated, unprivileged environment.
- Blender parses complex third-party file formats and addons. Run it with an unprivileged account in an isolated container, with no sensitive host mounts. The worker passes `--disable-autoexec` so a .blend project's automatic Python scripts do not run during diagnostics.
- Use backups before modifying \`.blend\` files or invoking Fast64 exporters. Fast64 may modify project files and may crash on some material operations.
- The Android-facing GitHub Actions diagnostic accepts only a relative .blend path below `inbox/`, runs with read-only repository permissions, and publishes only a JSON artifact. It does not execute arbitrary uploaded Python scripts or write to the repository. Blender file parsing remains a risk; use only trusted files.
- Do not expose stdio or a development HTTP server to the public Internet.
- A future remote deployment must implement HTTPS, OAuth 2.1, per-user authorization, tenant isolation, rate limits, upload quarantine and audit logging.
- Operator discovery is not proof that an export will work. Some Fast64 operators need UI context, configured projects, F3D materials, or other scene-specific state.
