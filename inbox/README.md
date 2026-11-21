# Blender diagnostic input

Upload a \`.blend\` project into this folder using GitHub's web interface, then run **Actions → Blender Project Diagnostics** and provide the repository path, for example:

\`inbox/Steve.blend\`

Keep relative textures and supporting files in folders beside the \`.blend\` file. The diagnostic workflow opens the project with Blender automatic Python execution disabled and only runs the read-only asset-pipeline inspector. It returns a \`blender-pipeline-report\` artifact; it does not modify the uploaded project.

Do not upload confidential projects or credentials. Blender file parsing still processes complex binary data, so only use files you trust.
