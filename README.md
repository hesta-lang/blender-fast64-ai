# Blender Fast64 AI Bridge

**0.1.0-alpha** — puente experimental MCP para controlar Blender y consultar Fast64 desde un cliente compatible.

> **Estado real:** alpha local por stdio. No está conectado automáticamente a ChatGPT. La conexión remota personalizada depende del plan y la interfaz compatibles; la app móvil no permite configurar servidores MCP personalizados. Consulta [CHATGPT_SETUP.md](docs/CHATGPT_SETUP.md).

## Arquitectura

```
Cliente MCP (local)
       | stdio
       v
Servidor MCP (server/)
       | JSON validado
       v
Blender --background (blender_runner/)
       +-- bpy: inspección, importación y transformaciones
       +-- Fast64: diagnóstico y descubrimiento de exportadores
```

## Herramientas implementadas en esta alpha

| Herramienta | Función |
|---|---|
| `workspace_status` | Versión de Blender, proyecto y detección de Fast64 |
| `inspect_scene` | Objetos, mallas, materiales y armatures |
| `list_objects` | Lista de objetos |
| `rename_object` | Renombra un objeto |
| `set_object_transform` | Cambia ubicación, rotación y escala |
| `import_model` | Importa archivos desde `data/workspace/imports/` |
| `fast64_diagnostics` | Diagnóstico de módulos Fast64 |
| `fast64_export_operators` | Descubre operadores de exportación registrados |
| `save_project` | Guarda la escena como `active.blend` |

No se expone una consola Python ni una shell arbitraria al modelo. Las operaciones se ejecutan mediante un dispatcher cerrado.

## Requisitos

- Python 3.11+
- Blender instalado y accesible como `blender`.
- Fast64 instalado y habilitado en Blender para utilizar sus funciones.
- Docker opcional.

## Desarrollo local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m server.main
```

El servidor utiliza MCP por stdio. No expongas esta versión a Internet: todavía no incorpora OAuth remoto, TLS, aislamiento multiusuario ni una interfaz de carga autenticada.

## Fast64

Fast64 es un addon de Blender para exportar assets F3D/N64, incluidos proyectos de Super Mario 64. Los operadores disponibles dependen de la versión y de la escena. Descubrir un operador no garantiza que su exportación funcione sin el contexto y los materiales adecuados.

- [Fast64](https://github.com/Fast-64/fast64)
- [Documentación SM64](https://github.com/Fast-64/fast64/tree/main/fast64_internal/sm64)

## Seguridad y limitaciones

- Importa solo archivos que hayas revisado; los formatos 3D pueden contener datos maliciosos.
- Los nombres de archivo se limitan a nombres simples y extensiones permitidas.
- No se permite ejecutar código arbitrario desde ChatGPT.
- Usa copias de seguridad de tus proyectos.
- El contenedor incluido es una base de desarrollo, no una configuración lista para producción.
- Aún no se ha validado una exportación DynOS real ni la ejecución en Blender/Fast64.

Consulta [docs/SECURITY.md](docs/SECURITY.md) y [docs/CHATGPT_SETUP.md](docs/CHATGPT_SETUP.md).

## Licencia

MIT.
