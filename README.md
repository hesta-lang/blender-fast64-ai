# Blender Fast64 AI Bridge

**0.3.0-alpha** — puente experimental MCP para crear y modificar escenas en Blender y descubrir/ejecutar exportadores Fast64 instalados.

> **Estado real:** alpha local por stdio. No está conectado automáticamente a ChatGPT. La conexión remota personalizada depende del plan y la interfaz compatibles; la app móvil no permite configurar servidores MCP personalizados. Consulta [CHATGPT_SETUP.md](docs/CHATGPT_SETUP.md).

## Arquitectura

```text
Cliente MCP local
      | stdio
      v
Servidor MCP (server/)
      | acciones JSON validadas
      v
Blender --background (blender_runner/)
      +-- modelado: creación de mallas y UVs
      +-- rigging: armatures, auto weights y pesos explícitos
      +-- persistencia: carga automática de active.blend y backup .blend1
      +-- materiales: Principled BSDF e imágenes, conversión nativa a F3D
      +-- SM64: pesos binarios por vértice y exportador real de geolayout C
```

## Herramientas

| Herramienta | Función |
|---|---|
| `workspace_status` / `inspect_scene` | Estado de Blender, escena, mallas, materiales, imágenes y huesos |
| `list_objects`, `rename_object`, `set_object_transform` | Gestión de objetos |
| `import_model` | Importa BLEND, FBX, OBJ, GLB, GLTF, STL o PLY desde `data/workspace/imports/` |
| `create_mesh_object` | Crea una malla Blender editable desde vértices y caras; límite 50.000 vértices/caras |
| `smart_uv_unwrap` | Genera UVs mediante Smart UV Project |
| `create_armature` | Crea un esqueleto de huesos con jerarquía padre-hijo |
| `bind_mesh_to_armature` | Intenta rigging automático de Blender (bone heat) |
| `set_vertex_weights` | Aplica pesos explícitos por vértice y hueso |
| `create_material` | Crea material Principled BSDF y opcionalmente carga imagen desde `imports/` |
| `convert_materials_to_f3d` | Usa el conversor oficial de Fast64 para convertir materiales Principled en materiales F3D nativos |
| `assign_material` | Asigna un material existente a una malla |
| `set_sm64_binary_skinning` | Asigna exactamente un hueso deformador con peso 1.0 a cada vértice, para la skinning binaria de SM64 |
| `export_sm64_armature` | Ejecuta el exportador de geolayout de armature C de Fast64; escribe debajo de `exports/` |
| `fast64_diagnostics` | Detecta módulos, addon habilitado y espacios de operadores |
| `fast64_export_operators` | Descubre operadores de exportación y expone sus propiedades |
| `fast64_run_export` | Ejecuta un operador de exportación detectado, con propiedades validadas y rutas restringidas a `exports/` |
| `save_project` | Guarda la escena como `data/workspace/active.blend` |

No se expone una consola Python, shell, ni ejecución de código arbitrario. El dispatcher solo acepta acciones definidas. Los datos de malla, huesos, pesos, colores y rutas se validan antes de llegar a Blender.

## Uso de archivos

Coloca modelos y texturas que quieras importar en `data/workspace/imports/`. Texturas soportadas por `create_material`: PNG, JPG/JPEG, TGA, TIFF, BMP y EXR. Las exportaciones Fast64 deben guardarse dentro de `data/workspace/exports/`.

## Requisitos

- Python 3.11+
- Blender instalado y accesible como `blender`.
- Fast64 instalado y habilitado en Blender para exportar assets F3D/N64.
- Docker opcional.

## Desarrollo local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m server.main
```

El servidor utiliza MCP por stdio. Cada llamada de Blender carga `data/workspace/active.blend`; las operaciones que modifican la escena guardan el archivo automáticamente y Blender conserva `active.blend1` como copia de seguridad. No expongas esta versión a Internet: todavía no incorpora OAuth remoto, TLS, aislamiento multiusuario ni una interfaz de carga autenticada.

## Fast64

Fast64 no exporta un formato universal: genera recursos F3D/N64 y assets específicos de proyectos como Super Mario 64. Para exportar modelos, Fast64 requiere materiales F3D compatibles; un material Principled BSDF estándar no equivale a un material F3D. `convert_materials_to_f3d` llama al conversor oficial `object.convert_bsdf` del addon y valida que los materiales hayan quedado marcados como F3D. La skinning binaria de SM64 asigna un único hueso deformador a cada vértice, con peso 1.0; los pesos suaves de rigging automático no son adecuados para este formato. `export_sm64_armature` ejecuta `object.sm64_export_geolayout_armature` en modo C con ruta de salida personalizada dentro de `exports/`. Esto genera archivos C de Fast64; no es un exportador DynOS.

- [Fast64](https://github.com/Fast-64/fast64)
- [Documentación de exportación SM64](https://github.com/Fast-64/fast64/tree/main/fast64_internal/sm64)

## Prueba DynOS: Mario Star

La CI genera una variante del modelo oficial de Coop Deluxe: gorra azul y emblema dorado. Mantiene el armature, los grupos de vértices y las acciones de animación originales.

El exportador Fast64-Gart crea inicialmente `Assets/mario/`. El empaquetador de esta alpha aplana esa carpeta para que la estructura final sea:

```text
dynos/packs/MarioStar/
  Assets/
    geo.inc.c
    geo_header.h
    model.inc.c
    mario/
      *.png
  README.txt
```

La ubicación de los fuentes es obligatoria: el generador de SM64CoopDX recorre las carpetas inmediatas del pack y busca `model.inc.c` y `geo.inc.c` dentro de cada una. Las imágenes deben permanecer en `Assets/mario/`, porque `model.inc.c` las referencia con rutas como `Assets/mario/mario_eyes_center.rgba16.inc.c`; DynOS resuelve esas inclusiones buscando el PNG correspondiente. No aplanes las imágenes junto a los fuentes.

Para probarlo, copia la carpeta `MarioStar` a `dynos/packs/`, elimina cualquier `mario_geo.bin` antiguo de ese pack y abre el juego. SM64CoopDX generará `mario_geo.bin` en la raíz de `MarioStar`. Después activa `MarioStar` en **Options > DynOS Packs**. Esta variante reemplaza el modelo de Mario; no agrega una entrada de personaje separada llamada “Mario Star”.

El artifact `mario-star-dynos-source-pack` incluye el ZIP del pack, el proyecto Blender y un informe JSON. La CI valida la estructura de fuentes, que cada inclusión de textura tenga su PNG correspondiente y la exportación Fast64-Gart, pero no inicia el juego; la prueba visual final sigue pendiente.

## Limitaciones de esta alpha

- El modelado genera geometría real a partir de vértices/caras proporcionados; no crea por sí solo un modelo artístico completo desde una descripción de texto.
- El rigging automático depende de la topología y puede fallar con mallas desconectadas o geometría no adecuada. Los pesos explícitos permiten corregirlo manualmente.
- La prueba de integración instala Fast64 desde un commit fijado y valida la conversión F3D y la exportación de un geolayout SM64 C de prueba en Blender `--background`.
- El exportador Fast64 SM64 C no genera formato DynOS. Los proyectos de juego pueden requerir conversión o integración adicional fuera de este puente.
- Fast64 puede exigir ajustes de geolayout, jerarquía de huesos y materiales específicos para el modelo real; el test mínimo no sustituye la validación del asset final.
- No se ha implementado todavía un servidor remoto autenticado conectable desde ChatGPT móvil.

Importa solo archivos revisados: los formatos 3D pueden contener datos maliciosos. Usa backups antes de probar operadores de exportación. El contenedor es una base de desarrollo, no una configuración de producción.

Consulta [docs/SECURITY.md](docs/SECURITY.md) y [docs/CHATGPT_SETUP.md](docs/CHATGPT_SETUP.md).

## Licencia

MIT.
