# Blender Fast64 AI Bridge

**0.1.0-alpha** — puente experimental entre un cliente MCP, Blender y Fast64.

Este repositorio permite que un cliente MCP compatible invoque herramientas limitadas para inspeccionar y modificar una escena de Blender. Fast64 se carga como complemento de Blender y sus operadores se descubren en tiempo de ejecución.

> **Estado:** prototipo. No está conectado automáticamente a ChatGPT. Para conectar un servidor remoto desde ChatGPT se necesita un plan y una superficie compatibles con MCP personalizado; la app móvil no permite configurar servidores MCP personalizados. Consulta [CHATGPT_SETUP.md](docs/CHATGPT_SETUP.md).

## Arquitectura

```
ChatGPT web / cliente MCP
       | HTTPS + OAuth (despliegue remoto)
       v
Servidor MCP (server/)
       | JSON validado
       v
Blender --background (blender_runner/)
       | bpy
       +-- escena, mallas, materiales, armatures
       +-- Fast64: diagnóstico y exportación
```

## Funciones iniciales

- Estado de Blender y diagnóstico de Fast64.
- Inspección de escena y listado de objetos.
- Crear mallas, importar modelos y transformar objetos.
- Crear armatures, huesos y enlazar mallas.
- Materiales y texturas.
- Descubrir operadores de exportación Fast64.
- Guardar proyecto y crear backups.

No se expone una consola Python ni una shell arbitraria al modelo. Las operaciones se validan y se ejecutan mediante un dispatcher cerrado.

## Requisitos

- Python 3.11+
- Blender instalado (probado pendiente).
- Fast64 instalado en Blender (probado pendiente).
- Docker opcional para despliegue reproducible.

## Inicio de desarrollo

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m server.main
```

El modo local usa MCP por stdio. No lo expongas a Internet. El despliegue remoto debe añadir HTTPS, OAuth 2.1, validación de issuer/audience/scopes, aislamiento por propietario, límites de peticiones y almacenamiento persistente.

## Fast64

Fast64 es un addon de Blender para exportar assets F3D/N64, incluidos proyectos de Super Mario 64. No todos los operadores son utilizables sin contexto de UI o configuración de escena. El puente descubre operadores reales y no presupone que una exportación vaya a funcionar sin validación.

- [Fast64](https://github.com/Fast-64/fast64)
- [Documentación SM64](https://github.com/Fast-64/fast64/tree/main/fast64_internal/sm64)

## Seguridad y limitaciones

- Trabaja sobre copias del archivo .blend.
- Los archivos importados deben estar en el directorio de imports.
- Los nombres y parámetros se validan antes de enviarlos a Blender.
- Los exportadores se seleccionan de la lista descubierta; no se ejecuta código arbitrario.
- Este prototipo no implementa todavía aislamiento multiusuario ni OAuth remoto listo para producción.
- No se ha validado una exportación DynOS real ni una sesión gráfica de Blender.

Lee [docs/SECURITY.md](docs/SECURITY.md) antes de desplegarlo.

## Licencia

MIT.
