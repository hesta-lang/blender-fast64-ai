# Blender Fast64 AI Bridge

**0.2.0-alpha** — puente experimental MCP para crear y modificar escenas en Blender y descubrir/ejecutar exportadores Fast64 instalados.

> **Estado real:** alpha local por stdio. No está conectado automáticamente a ChatGPT. La conexión remota personalizada depende del plan y la interfaz compatibles; la app móvil no permite configurar servidores MCP personalizados. Consulta [CHATGPT_SETUP.md](docs/CHATGPT_SETUP.md).

## Arquitectura

\`\`\`text
Cliente MCP local
      | stdio
      v
Servidor MCP (server/)
      | acciones JSON validadas
      v
Blender --background (blender_runner/)
      +-- modelado: creación de mallas y UVs
      +-- rigging: armatures, auto weights y pesos explícitos
      +-- materiales: Principled BSDF e imágenes
      +-- Fast64: diagnóstico, catálogo y ejecución restringida de exportadores
\`\`\`

## Herramientas

| Herramienta | Función |
|---|---|
| \`workspace_status\` / \`inspect_scene\` | Estado de Blender, escena, mallas, materiales, imágenes y huesos |
| \`list_objects\`, \`rename_object\`, \`set_object_transform\` | Gestión de objetos |
| \`import_model\` | Importa BLEND, FBX, OBJ, GLB, GLTF, STL o PLY desde \`data/workspace/imports/\` |
| \`create_mesh_object\` | Crea una malla Blender editable desde vértices y caras; límite 50.000 vértices/caras |
| \`smart_uv_unwrap\` | Genera UVs mediante Smart UV Project |
| \`create_armature\` | Crea un esqueleto de huesos con jerarquía padre-hijo |
| \`bind_mesh_to_armature\` | Intenta rigging automático de Blender (bone heat) |
| \`set_vertex_weights\` | Aplica pesos explícitos por vértice y hueso |
| \`create_material\` | Crea material Principled BSDF y opcionalmente carga imagen desde \`imports/\` |
| \`assign_material\` | Asigna un material existente a una malla |
| \`fast64_diagnostics\` | Detecta módulos, addon habilitado y espacios de operadores |
| \`fast64_export_operators\` | Descubre operadores de exportación y expone sus propiedades |
| \`fast64_run_export\` | Ejecuta un operador de exportación detectado, con propiedades validadas y rutas restringidas a \`exports/\` |
| \`save_project\` | Guarda la escena como \`data/workspace/active.blend\` |

No se expone una consola Python, shell, ni ejecución de código arbitrario. El dispatcher solo acepta acciones definidas. Los datos de malla, huesos, pesos, colores y rutas se validan antes de llegar a Blender.

## Uso de archivos

Coloca modelos y texturas que quieras importar en \`data/workspace/imports/\`. Texturas soportadas por \`create_material\`: PNG, JPG/JPEG, TGA, TIFF, BMP y EXR. Las exportaciones Fast64 deben guardarse dentro de \`data/workspace/exports/\`.

## Requisitos

- Python 3.11+
- Blender instalado y accesible como \`blender\`.
- Fast64 instalado y habilitado en Blender para exportar assets F3D/N64.
- Docker opcional.

## Desarrollo local

\`\`\`bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m server.main
\`\`\`

El servidor utiliza MCP por stdio. No expongas esta versión a Internet: todavía no incorpora OAuth remoto, TLS, aislamiento multiusuario ni una interfaz de carga autenticada.

## Fast64

Fast64 no exporta un formato universal: genera recursos F3D/N64 y assets específicos de proyectos como Super Mario 64. Para exportar modelos, Fast64 requiere materiales F3D compatibles; un material Principled BSDF estándar no equivale a un material F3D. El puente puede descubrir los operadores que estén registrados en la versión local y ejecutarlos si aceptan las propiedades suministradas, pero no puede garantizar el éxito de un export sin proyecto, selección, materiales y contexto adecuados.

- [Fast64](https://github.com/Fast-64/fast64)
- [Documentación de exportación SM64](https://github.com/Fast-64/fast64/tree/main/fast64_internal/sm64)

## Limitaciones de esta alpha

- El modelado genera geometría real a partir de vértices/caras proporcionados; no crea por sí solo un modelo artístico completo desde una descripción de texto.
- El rigging automático depende de la topología y puede fallar con mallas desconectadas o geometría no adecuada. Los pesos explícitos permiten corregirlo manualmente.
- Los materiales Principled son materiales Blender normales. Fast64 necesita sus propios materiales F3D y configuración específica.
- Los operadores Fast64 pueden requerir contexto de interfaz, proyecto decomp, materiales F3D y selección de objetos. El trabajador corre en \`--background\`, así que algunos operadores no serán ejecutables en este contexto.
- No se ha validado en una instalación real de Blender + Fast64 ni se ha completado una exportación DynOS real.
- No se ha implementado todavía un servidor remoto autenticado conectable desde ChatGPT móvil.

Importa solo archivos revisados: los formatos 3D pueden contener datos maliciosos. Usa backups antes de probar operadores de exportación. El contenedor es una base de desarrollo, no una configuración de producción.

Consulta [docs/SECURITY.md](docs/SECURITY.md) y [docs/CHATGPT_SETUP.md](docs/CHATGPT_SETUP.md).

## Licencia

MIT.
