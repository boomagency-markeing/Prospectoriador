# AI Prospecting Agent — Colombia

Agente B2B para descubrir, investigar, calificar y priorizar empresas medianas/grandes
que puedan contratar servicios de tráfico digital.

## Pipeline

1. Discovery: busca empresas por ciudad + sector.
2. Entity resolution: deduplica por dominio/nombre.
3. Company intelligence: analiza website y resultados.
4. Digital audit: identifica señales de Ads, SEO, ecommerce, formularios, WhatsApp y conversión.
5. Contact intelligence: prioriza canales corporativos/profesionales.
6. Evidence graph: cada afirmación importante conserva fuente, URL, fecha y confianza.
7. AI qualification: produce ICP score, opportunity score, dolor, servicio recomendado y explicación.
8. Sales queue: ordena A+, A, B, C y prepara el contexto para contacto.

## Ejecutar

Windows:
- Ejecuta `run_windows.bat`
- Abre http://127.0.0.1:8000

Manual:
- `python -m pip install -r requirements.txt`
- Copia `.env.example` a `.env`
- Añade TAVILY_API_KEY.
- Añade OPENAI_API_KEY si quieres análisis IA.
- `uvicorn app.main:app --reload`

Sin claves, el agente funciona en modo demo.

## Importante

La aplicación NO envía emails automáticamente. Primero investiga y genera una cola
de contactos. La automatización de outreach debe añadirse después de validar los
datos, consentimiento/base jurídica, opt-out y políticas de la infraestructura de
correo.

La búsqueda de contactos prioriza datos corporativos y profesionales públicos.
No intenta descubrir contraseñas, datos privados ni información innecesaria.
