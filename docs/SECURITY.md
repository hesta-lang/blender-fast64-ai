# Security notes

This is an early local-development alpha.

- No arbitrary Python, shell or filesystem tool is exposed to the model.
- Import filenames are restricted to plain basenames and allowed extensions.
- Blender operations are routed through a fixed action dispatcher.
- Do not expose stdio or a development HTTP server to the public Internet.
- A future remote deployment must implement OAuth 2.1, TLS, per-user authorization, tenant isolation, rate limits, upload quarantine and audit logging.
- Treat .blend and imported model files as untrusted. Run Blender in an isolated, unprivileged container with no sensitive host mounts.
- Fast64 operator discovery is not proof that an export will work; some operators need specific scene/UI context and material setup.
