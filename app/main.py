import os
import re
import json
import sqlite3
import hashlib
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates


# ============================================================
# CONFIGURACIÓN
# ============================================================

load_dotenv()

ROOT = os.path.dirname(os.path.dirname(__file__))

DB = os.path.join(
    ROOT,
    "prospecting_agent.db"
)

templates = Jinja2Templates(
    directory=os.path.join(ROOT, "templates")
)

app = FastAPI(
    title="AI Prospecting Agent",
    version="1.0"
)


# ============================================================
# CIUDADES
# ============================================================

CITIES = [
    ("Bogotá D.C.", "Bogotá D.C."),
    ("Medellín", "Antioquia"),
    ("Cali", "Valle del Cauca"),
    ("Barranquilla", "Atlántico"),
    ("Bucaramanga", "Santander"),
    ("Cartagena", "Bolívar"),
    ("Pereira", "Risaralda"),
    ("Manizales", "Caldas"),
    ("Armenia", "Quindío"),
]


# ============================================================
# SECTORES
# ============================================================

SECTORS = [
    "Salud",
    "Educación",
    "Retail / Ecommerce",
    "Inmobiliario",
    "Automotriz",
    "Servicios B2B",
    "Turismo / Hotelería",
    "Financiero",
    "Industria",
    "Tecnología",
    "Logística",
]


# ============================================================
# UTILIDADES
# ============================================================

def now():
    return datetime.now(timezone.utc).isoformat()


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


# ============================================================
# BASE DE DATOS
# ============================================================

def init_db():

    c = db()

    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS companies(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            domain TEXT,
            city TEXT,
            department TEXT,
            sector TEXT,
            website TEXT,
            description TEXT,
            employee_signal TEXT,
            size_class TEXT,
            size_confidence TEXT,
            advertising_signal TEXT,
            seo_signal TEXT,
            ecommerce INTEGER DEFAULT 0,
            lead_gen INTEGER DEFAULT 0,
            whatsapp INTEGER DEFAULT 0,
            multi_site INTEGER DEFAULT 0,
            growth_signal TEXT,
            pain_point TEXT,
            recommended_service TEXT,
            icp_score INTEGER DEFAULT 0,
            opportunity_score INTEGER DEFAULT 0,
            priority TEXT DEFAULT 'C',
            confidence TEXT,
            status TEXT DEFAULT 'Nuevo',
            opt_out INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(company, city)
        );

        CREATE TABLE IF NOT EXISTS contacts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER,
            name TEXT,
            title TEXT,
            email TEXT,
            email_type TEXT,
            linkedin TEXT,
            source_url TEXT,
            confidence TEXT,
            priority INTEGER DEFAULT 0,
            opt_out INTEGER DEFAULT 0,
            checked_at TEXT
        );

        CREATE TABLE IF NOT EXISTS evidence(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER,
            evidence_type TEXT,
            claim TEXT,
            url TEXT,
            source_title TEXT,
            confidence TEXT,
            checked_at TEXT
        );

        CREATE TABLE IF NOT EXISTS jobs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT,
            sector TEXT,
            status TEXT,
            discovered INTEGER DEFAULT 0,
            qualified INTEGER DEFAULT 0,
            created_at TEXT,
            finished_at TEXT,
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS research_notes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER,
            note_type TEXT,
            content TEXT,
            created_at TEXT
        );
        """
    )

    c.commit()
    c.close()


init_db()


# ============================================================
# DOMINIO
# ============================================================

def domain_of(url):

    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


# ============================================================
# TAVILY
# ============================================================

def tavily(query, n=None):

    print("")
    print("=" * 70)
    print("TAVILY - INICIANDO BÚSQUEDA")
    print("=" * 70)
    print(f"QUERY: {query}")

    key = os.getenv("TAVILY_API_KEY")

    if not key:
        error = (
            "TAVILY_API_KEY no está configurada "
            "en las variables de entorno de Render."
        )

        print("ERROR:", error)

        raise RuntimeError(error)

    try:

        n = n or int(
            os.getenv(
                "MAX_SEARCH_RESULTS",
                "8"
            )
        )

        print(f"RESULTADOS SOLICITADOS: {n}")
        print("ENVIANDO SOLICITUD A TAVILY...")

        r = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": key,
                "query": query,
                "search_depth": "advanced",
                "max_results": n,
                "include_answer": False,
            },
            timeout=45,
        )

        print(
            f"TAVILY HTTP STATUS: {r.status_code}"
        )

        if r.status_code != 200:

            print(
                "RESPUESTA DE ERROR DE TAVILY:"
            )

            print(
                r.text[:2000]
            )

        r.raise_for_status()

        data = r.json()

        results = data.get(
            "results",
            []
        )

        print(
            f"TAVILY DEVOLVIÓ {len(results)} RESULTADOS"
        )

        for index, result in enumerate(
            results[:5],
            start=1
        ):

            print(
                f"RESULTADO {index}: "
                f"{result.get('title', '')} | "
                f"{result.get('url', '')}"
            )

        print("=" * 70)
        print("TAVILY - BÚSQUEDA FINALIZADA")
        print("=" * 70)
        print("")

        return results

    except requests.exceptions.Timeout as e:

        print("")
        print("=== ERROR TAVILY: TIMEOUT ===")
        print(str(e))
        print("")

        raise RuntimeError(
            "Tavily tardó demasiado en responder."
        ) from e

    except requests.exceptions.HTTPError as e:

        print("")
        print("=== ERROR TAVILY: HTTP ===")
        print(str(e))

        try:
            print(
                "RESPUESTA:",
                r.text[:2000]
            )
        except Exception:
            pass

        print("")

        raise RuntimeError(
            f"Tavily devolvió un error HTTP "
            f"{getattr(r, 'status_code', 'desconocido')}."
        ) from e

    except requests.exceptions.RequestException as e:

        print("")
        print("=== ERROR TAVILY: REQUEST ===")
        print(str(e))
        print("")

        raise RuntimeError(
            f"Error de conexión con Tavily: {str(e)}"
        ) from e

    except Exception as e:

        print("")
        print("=== ERROR TAVILY: GENERAL ===")
        print(str(e))
        traceback.print_exc()
        print("")

        raise


# ============================================================
# OBTENER CONTENIDO DE PÁGINA
# ============================================================

def fetch_page(url):

    if not url.startswith(
        ("http://", "https://")
    ):
        return ""

    try:

        r = requests.get(
            url,
            headers={
                "User-Agent":
                    "AI-Prospecting-Agent/1.0"
            },
            timeout=20,
            allow_redirects=True,
        )

        if "text/html" not in r.headers.get(
            "content-type",
            ""
        ):
            return ""

        soup = BeautifulSoup(
            r.text,
            "html.parser"
        )

        for x in soup(
            ["script", "style", "noscript"]
        ):
            x.decompose()

        text = soup.get_text(
            " ",
            strip=True
        )

        return re.sub(
            r"\s+",
            " ",
            text
        )[:18000]

    except Exception as e:

        print(
            f"ERROR OBTENIENDO PÁGINA {url}: {e}"
        )

        return ""


# ============================================================
# EXTRAER EMAILS
# ============================================================

def emails(text):

    vals = re.findall(
        r'[\w.+-]+@[\w-]+\.[\w.-]+',
        text or ""
    )

    return sorted(
        set(vals),
        key=lambda x: (
            not x.lower().startswith(
                (
                    "info@",
                    "contacto@",
                    "ventas@",
                    "comercial@",
                    "marketing@",
                    "gerencia@",
                )
            ),
            x,
        ),
    )


# ============================================================
# BUSCAR EMPRESAS
# ============================================================

def search_company(city, sector):

    print("")
    print("#" * 70)
    print("INICIANDO INVESTIGACIÓN")
    print(f"CIUDAD: {city}")
    print(f"SECTOR: {sector}")
    print("#" * 70)

    queries = [

        f"empresas {sector} medianas grandes {city} Colombia",

        f"{sector} {city} Colombia empresa director marketing comercial",

        f'{sector} {city} Colombia "contacto" empresa',

        f"{sector} {city} Colombia publicidad Google Ads Meta Ads",

    ]

    allr = []

    for index, q in enumerate(
        queries,
        start=1
    ):

        print("")
        print(
            f"BUSCANDO QUERY {index}/{len(queries)}"
        )

        results = tavily(q)

        allr += results

        print(
            f"RESULTADOS ACUMULADOS: {len(allr)}"
        )

    seen = set()
    out = []

    for r in allr:

        url = r.get(
            "url",
            ""
        )

        d = domain_of(url)

        if not d:
            continue

        if d in seen:
            continue

        seen.add(d)

        out.append(
            {
                "title":
                    r.get(
                        "title",
                        ""
                    ),

                "url":
                    url,

                "domain":
                    d,

                "content":
                    r.get(
                        "content",
                        ""
                    )[:6000],
            }
        )

    print("")
    print(
        f"EMPRESAS ÚNICAS ENCONTRADAS: {len(out)}"
    )

    if not out:

        print(
            "TAVILY NO DEVOLVIÓ EMPRESAS."
        )

        return []

    return out[:30]


# ============================================================
# SEÑALES LOCALES
# ============================================================

def local_signals(text):

    t = (
        text or ""
    ).lower()

    return {

        "ecommerce": int(
            any(
                x in t
                for x in [
                    "tienda online",
                    "ecommerce",
                    "comprar en línea",
                    "carrito",
                    "shop",
                ]
            )
        ),

        "lead_gen": int(
            any(
                x in t
                for x in [
                    "cotiza",
                    "solicita una cotización",
                    "agenda",
                    "formulario",
                    "contáctanos",
                    "contacto",
                ]
            )
        ),

        "whatsapp": int(
            "whatsapp" in t
        ),

        "multi_site": int(
            any(
                x in t
                for x in [
                    "sedes",
                    "nuestras sedes",
                    "sucursal",
                    "sucursales",
                ]
            )
        ),
    }


# ============================================================
# SCORE
# ============================================================

def rule_score(p):

    icp = 0
    opp = 0

    if p["size_class"] == "Mediana":
        icp += 20

    elif p["size_class"] == "Grande":
        icp += 25

    elif p["employee_signal"]:
        icp += 8

    if p["sector"] in {
        "Salud",
        "Educación",
        "Retail / Ecommerce",
        "Inmobiliario",
        "Automotriz",
        "Servicios B2B",
        "Turismo / Hotelería",
        "Financiero",
        "Tecnología",
    }:
        icp += 10

    if p["website"]:
        icp += 5

    if p["lead_gen"]:
        opp += 10

    if p["ecommerce"]:
        opp += 10

    if p["advertising_signal"] not in (
        "",
        "No detectado"
    ):
        opp += 15

    if p["seo_signal"] not in (
        "",
        "No evaluado"
    ):
        opp += 5

    if p["whatsapp"]:
        opp += 5

    if p["multi_site"]:
        opp += 5

    if p["growth_signal"]:
        opp += 10

    if p["pain_point"]:
        opp += 10

    total = min(
        100,
        icp + opp
    )

    priority = (
        "A+"
        if total >= 85
        else "A"
        if total >= 70
        else "B"
        if total >= 50
        else "C"
    )

    return (
        min(icp, 100),
        total,
        priority
    )


# ============================================================
# OPENAI
# ============================================================

def ai_analyze(payload):

    key = os.getenv(
        "OPENAI_API_KEY"
    )

    if not key:

        print(
            "OPENAI_API_KEY no configurada. "
            "Se utilizará scoring por reglas."
        )

        return None

    model = os.getenv(
        "OPENAI_MODEL",
        "gpt-5-mini"
    )

    print("")
    print("=" * 70)
    print("OPENAI - INICIANDO ANÁLISIS")
    print(f"MODELO: {model}")
    print("=" * 70)

    schema = {

        "name":
            "prospect_analysis",

        "schema": {

            "type":
                "object",

            "additionalProperties":
                False,

            "properties": {

                "size_class": {
                    "type": "string",
                    "enum": [
                        "Grande",
                        "Mediana",
                        "Pequeña",
                        "No determinado",
                    ],
                },

                "size_confidence": {
                    "type": "string",
                    "enum": [
                        "Alta",
                        "Media",
                        "Baja",
                    ],
                },

                "advertising_signal": {
                    "type": "string"
                },

                "seo_signal": {
                    "type": "string"
                },

                "growth_signal": {
                    "type": "string"
                },

                "pain_point": {
                    "type": "string"
                },

                "recommended_service": {
                    "type": "string"
                },

                "icp_score": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                },

                "opportunity_score": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                },

                "priority": {
                    "type": "string",
                    "enum": [
                        "A+",
                        "A",
                        "B",
                        "C",
                    ],
                },

                "confidence": {
                    "type": "string",
                    "enum": [
                        "Alta",
                        "Media",
                        "Baja",
                    ],
                },

                "reason": {
                    "type": "string"
                },

                "contact_titles": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                },
            },

            "required": [
                "size_class",
                "size_confidence",
                "advertising_signal",
                "seo_signal",
                "growth_signal",
                "pain_point",
                "recommended_service",
                "icp_score",
                "opportunity_score",
                "priority",
                "confidence",
                "reason",
                "contact_titles",
            ],
        },
    }

    system = """
Eres un analista B2B de inteligencia comercial.

Solo puedes afirmar hechos respaldados por el material proporcionado.

Distingue HECHO de INFERENCIA.

No inventes ingresos, empleados, cargos, emails, publicidad ni crecimiento.

Tu objetivo es identificar si una empresa puede ser compradora de servicios
de tráfico digital como Meta Ads, Google Ads, LinkedIn Ads, CRO, analítica
o performance.

Prioriza empresas medianas y grandes.

Si el tamaño no está demostrado utiliza "No determinado".

Un score alto requiere evidencia de capacidad + necesidad.
"""

    user = f"""
Analiza esta empresa para prospección B2B.

DATOS:

{json.dumps(
    payload,
    ensure_ascii=False
)[:24000]}

Devuelve JSON siguiendo exactamente el esquema.
"""

    try:

        r = requests.post(
            "https://api.openai.com/v1/responses",

            headers={
                "Authorization":
                    f"Bearer {key}",

                "Content-Type":
                    "application/json",
            },

            json={
                "model":
                    model,

                "input": [
                    {
                        "role":
                            "system",

                        "content":
                            system,
                    },

                    {
                        "role":
                            "user",

                        "content":
                            user,
                    },
                ],

                "text": {
                    "format": {
                        "type":
                            "json_schema",

                        "name":
                            schema["name"],

                        "strict":
                            True,

                        "schema":
                            schema["schema"],
                    }
                },
            },

            timeout=90,
        )

        print(
            f"OPENAI HTTP STATUS: {r.status_code}"
        )

        if r.status_code != 200:

            print(
                "RESPUESTA DE ERROR OPENAI:"
            )

            print(
                r.text[:2000]
            )

        r.raise_for_status()

        data = r.json()

        text = data.get(
            "output_text",
            ""
        )

        if not text:

            for item in data.get(
                "output",
                []
            ):

                for c in item.get(
                    "content",
                    []
                ):

                    if c.get(
                        "type"
                    ) == "output_text":

                        text = c.get(
                            "text",
                            ""
                        )

        if not text:

            print(
                "OPENAI NO DEVOLVIÓ output_text."
            )

            return None

        result = json.loads(
            text
        )

        print(
            "OPENAI - ANÁLISIS COMPLETADO"
        )

        return result

    except requests.exceptions.Timeout as e:

        print("")
        print(
            "=== ERROR OPENAI: TIMEOUT ==="
        )
        print(str(e))
        print("")

        return None

    except requests.exceptions.HTTPError as e:

        print("")
        print(
            "=== ERROR OPENAI: HTTP ==="
        )
        print(str(e))

        try:
            print(
                r.text[:2000]
            )
        except Exception:
            pass

        print("")

        return None

    except Exception as e:

        print("")
        print(
            "=== ERROR OPENAI ==="
        )
        print(str(e))

        traceback.print_exc()

        print("")

        return None


# ============================================================
# EVIDENCIA
# ============================================================

def insert_evidence(
    cid,
    etype,
    claim,
    url,
    title="",
    conf="Media"
):

    c = db()

    c.execute(
        """
        INSERT INTO evidence(
            company_id,
            evidence_type,
            claim,
            url,
            source_title,
            confidence,
            checked_at
        )
        VALUES(?,?,?,?,?,?,?)
        """,
        (
            cid,
            etype,
            claim,
            url,
            title,
            conf,
            now(),
        ),
    )

    c.commit()
    c.close()


# ============================================================
# GUARDAR EMPRESA
# ============================================================

def save_company(p):

    icp, opp, prio = rule_score(p)

    c = db()

    c.execute(
        """
        INSERT INTO companies
        (
            company,
            domain,
            city,
            department,
            sector,
            website,
            description,
            employee_signal,
            size_class,
            size_confidence,
            advertising_signal,
            seo_signal,
            ecommerce,
            lead_gen,
            whatsapp,
            multi_site,
            growth_signal,
            pain_point,
            recommended_service,
            icp_score,
            opportunity_score,
            priority,
            confidence,
            created_at,
            updated_at
        )
        VALUES(
            ?,?,?,?,?,?,?,?,?,?,
            ?,?,?,?,?,?,?,?,?,?,
            ?,?,?,?,?
        )

        ON CONFLICT(company,city)
        DO UPDATE SET
            domain=excluded.domain,
            website=excluded.website,
            description=excluded.description,
            employee_signal=excluded.employee_signal,
            size_class=excluded.size_class,
            size_confidence=excluded.size_confidence,
            advertising_signal=excluded.advertising_signal,
            seo_signal=excluded.seo_signal,
            ecommerce=excluded.ecommerce,
            lead_gen=excluded.lead_gen,
            whatsapp=excluded.whatsapp,
            multi_site=excluded.multi_site,
            growth_signal=excluded.growth_signal,
            pain_point=excluded.pain_point,
            recommended_service=excluded.recommended_service,
            icp_score=excluded.icp_score,
            opportunity_score=excluded.opportunity_score,
            priority=excluded.priority,
            confidence=excluded.confidence,
            updated_at=excluded.updated_at
        """,
        (
            p["company"],
            p["domain"],
            p["city"],
            p.get(
                "department",
                ""
            ),
            p["sector"],
            p["website"],
            p.get(
                "description",
                ""
            ),
            p.get(
                "employee_signal",
                ""
            ),
            p["size_class"],
            p["size_confidence"],
            p["advertising_signal"],
            p["seo_signal"],
            p["ecommerce"],
            p["lead_gen"],
            p["whatsapp"],
            p["multi_site"],
            p["growth_signal"],
            p["pain_point"],
            p["recommended_service"],
            p["icp_score"],
            p["opportunity_score"],
            p["priority"],
            p["confidence"],
            now(),
            now(),
        ),
    )

    c.commit()

    row = c.execute(
        """
        SELECT id
        FROM companies
        WHERE company=? AND city=?
        """,
        (
            p["company"],
            p["city"],
        ),
    ).fetchone()

    cid = row["id"]

    c.close()

    return cid


# ============================================================
# AGREGAR CONTACTO
# ============================================================

def add_contact(
    cid,
    email,
    source,
    confidence="Media"
):

    if not email:
        return

    local = email.split(
        "@"
    )[0].lower()

    generic = local in {
        "info",
        "contacto",
        "ventas",
        "comercial",
        "marketing",
        "gerencia",
        "hola",
        "admin",
    }

    c = db()

    c.execute(
        """
        INSERT INTO contacts(
            company_id,
            email,
            email_type,
            source_url,
            confidence,
            priority,
            checked_at
        )
        VALUES(?,?,?,?,?,?,?)
        """,
        (
            cid,
            email,
            (
                "Genérico corporativo"
                if generic
                else "Profesional"
            ),
            source,
            confidence,
            (
                10
                if generic
                else 7
            ),
            now(),
        ),
    )

    c.commit()
    c.close()


# ============================================================
# INVESTIGACIÓN PRINCIPAL
# ============================================================

def investigate(
    city,
    sector,
    jobid
):

    print("")
    print("╔" + "═" * 68 + "╗")
    print(
        "║ INICIANDO AGENTE DE PROSPECCIÓN"
        + " " * 32
        + "║"
    )
    print(
        f"║ Ciudad: {city}"
        + " " * max(
            1,
            54 - len(city)
        )
        + "║"
    )
    print(
        f"║ Sector: {sector}"
        + " " * max(
            1,
            54 - len(sector)
        )
        + "║"
    )
    print("╚" + "═" * 68 + "╝")
    print("")

    candidates = search_company(
        city,
        sector
    )

    print(
        f"CANDIDATOS RECIBIDOS: {len(candidates)}"
    )

    count = 0
    qualified = 0

    if not candidates:

        print(
            "NO SE ENCONTRARON CANDIDATOS."
        )

        c = db()

        c.execute(
            """
            UPDATE jobs
            SET status=?,
                discovered=?,
                qualified=?,
                finished_at=?,
                error=?
            WHERE id=?
            """,
            (
                "Completado",
                0,
                0,
                now(),
                "Tavily no devolvió resultados.",
                jobid,
            ),
        )

        c.commit()
        c.close()

        return 0, 0

    for index, x in enumerate(
        candidates,
        start=1
    ):

        print("")
        print("-" * 70)
        print(
            f"PROCESANDO EMPRESA {index}/{len(candidates)}"
        )
        print(
            f"NOMBRE: {x['title']}"
        )
        print(
            f"DOMINIO: {x['domain']}"
        )
        print(
            f"URL: {x['url']}"
        )
        print("-" * 70)

        page = fetch_page(
            x["url"]
        )

        text = (
            x["content"]
            + " "
            + page
        )[:24000]

        sig = local_signals(
            text
        )

        p = {
            "company":
                x["title"][:180]
                or x["domain"],

            "domain":
                x["domain"],

            "city":
                city,

            "department":
                dict(CITIES).get(
                    city,
                    ""
                ),

            "sector":
                sector,

            "website":
                x["url"],

            "description":
                x["content"][:1000],

            "employee_signal":
                "",

            "size_class":
                "No determinado",

            "size_confidence":
                "Baja",

            "advertising_signal":
                "No detectado",

            "seo_signal":
                "No evaluado",

            **sig,

            "growth_signal":
                "",

            "pain_point":
                "",

            "recommended_service":
                "Auditoría de adquisición digital",

            "icp_score":
                0,

            "opportunity_score":
                0,

            "priority":
                "C",

            "confidence":
                "Media",
        }

        # ----------------------------------------------------
        # DETECTAR PUBLICIDAD
        # ----------------------------------------------------

        if any(
            k in text.lower()
            for k in [
                "google ads",
                "meta ads",
                "facebook ads",
                "instagram ads",
                "linkedin ads",
            ]
        ):

            p["advertising_signal"] = (
                "Señal de publicidad digital "
                "detectada en contenido público"
            )

        # ----------------------------------------------------
        # DETECTAR SEO
        # ----------------------------------------------------

        if (
            "google" in text.lower()
            and any(
                k in text.lower()
                for k in [
                    "search",
                    "seo",
                    "posicion",
                ]
            )
        ):

            p["seo_signal"] = (
                "Señales SEO visibles; "
                "requiere auditoría técnica"
            )

        # ----------------------------------------------------
        # EMAILS
        # ----------------------------------------------------

        em = emails(
            text
        )

        print(
            f"EMAILS ENCONTRADOS: {len(em)}"
        )

        # ----------------------------------------------------
        # OPENAI
        # ----------------------------------------------------

        ai = ai_analyze(
            p
            | {
                "source_excerpt":
                    text[:10000]
            }
        )

        if ai:

            p.update(
                {
                    k: ai[k]
                    for k in [
                        "size_class",
                        "size_confidence",
                        "advertising_signal",
                        "seo_signal",
                        "growth_signal",
                        "pain_point",
                        "recommended_service",
                        "icp_score",
                        "opportunity_score",
                        "priority",
                        "confidence",
                    ]
                }
            )

            p["ai_reason"] = ai.get(
                "reason",
                ""
            )

        else:

            print(
                "OPENAI NO PRODUJO ANÁLISIS. "
                "USANDO SCORE POR REGLAS."
            )

            (
                p["icp_score"],
                p["opportunity_score"],
                p["priority"],
            ) = rule_score(
                p
            )

        # ----------------------------------------------------
        # GUARDAR EMPRESA
        # ----------------------------------------------------

        cid = save_company(
            p
        )

        count += 1

        insert_evidence(
            cid,
            "Empresa",
            "Empresa descubierta mediante búsqueda web.",
            x["url"],
            x["title"],
            p["confidence"],
        )

        # ----------------------------------------------------
        # GUARDAR CONTACTOS
        # ----------------------------------------------------

        for e in em[:5]:

            add_contact(
                cid,
                e,
                x["url"],
                "Media"
            )

        # ----------------------------------------------------
        # CALIFICACIÓN
        # ----------------------------------------------------

        if p["priority"] in (
            "A+",
            "A"
        ):

            qualified += 1

        print(
            f"EMPRESA GUARDADA: {p['company']}"
        )

        print(
            f"SCORE: {p['opportunity_score']}"
        )

        print(
            f"PRIORIDAD: {p['priority']}"
        )

        time.sleep(
            0.15
        )

    # --------------------------------------------------------
    # FINALIZAR JOB
    # --------------------------------------------------------

    c = db()

    c.execute(
        """
        UPDATE jobs
        SET status=?,
            discovered=?,
            qualified=?,
            finished_at=?,
            error=?
        WHERE id=?
        """,
        (
            "Completado",
            count,
            qualified,
            now(),
            "",
            jobid,
        ),
    )

    c.commit()
    c.close()

    print("")
    print("=" * 70)
    print("INVESTIGACIÓN TERMINADA")
    print(f"EMPRESAS DESCUBIERTAS: {count}")
    print(f"EMPRESAS CALIFICADAS: {qualified}")
    print("=" * 70)
    print("")

    return count, qualified


# ============================================================
# HOME
# ============================================================

@app.get(
    "/",
    response_class=HTMLResponse
)
def home(
    request: Request
):

    c = db()

    companies = c.execute(
        """
        SELECT *
        FROM companies
        ORDER BY opportunity_score DESC,
                 id DESC
        LIMIT 150
        """
    ).fetchall()

    contacts = c.execute(
        """
        SELECT
            ct.*,
            co.company,
            co.city,
            co.sector,
            co.opportunity_score,
            co.priority

        FROM contacts ct

        JOIN companies co
            ON co.id = ct.company_id

        WHERE ct.opt_out=0
          AND co.opt_out=0

        ORDER BY
            co.opportunity_score DESC,
            ct.priority DESC

        LIMIT 100
        """
    ).fetchall()

    jobs = c.execute(
        """
        SELECT *
        FROM jobs
        ORDER BY id DESC
        LIMIT 25
        """
    ).fetchall()

    stats = {

        "companies":
            c.execute(
                """
                SELECT COUNT(*) n
                FROM companies
                """
            ).fetchone()["n"],

        "qualified":
            c.execute(
                """
                SELECT COUNT(*) n
                FROM companies
                WHERE priority IN ('A+','A')
                """
            ).fetchone()["n"],

        "contacts":
            c.execute(
                """
                SELECT COUNT(*) n
                FROM contacts
                WHERE opt_out=0
                """
            ).fetchone()["n"],

        "high":
            c.execute(
                """
                SELECT COUNT(*) n
                FROM companies
                WHERE opportunity_score>=85
                """
            ).fetchone()["n"],
    }

    c.close()

    return templates.TemplateResponse(
        "index.html",
        {
            "request":
                request,

            "companies":
                companies,

            "contacts":
                contacts,

            "jobs":
                jobs,

            "stats":
                stats,

            "cities":
                CITIES,

            "sectors":
                SECTORS,
        },
    )


# ============================================================
# EJECUTAR AGENTE
# ============================================================

@app.post(
    "/agent/run"
)
def run_agent(
    city: str = Form(...),
    sector: str = Form(...)
):

    print("")
    print("=" * 70)
    print("NUEVA EJECUCIÓN DEL AGENTE")
    print(f"CIUDAD: {city}")
    print(f"SECTOR: {sector}")
    print("=" * 70)
    print("")

    c = db()

    cur = c.execute(
        """
        INSERT INTO jobs(
            city,
            sector,
            status,
            created_at
        )
        VALUES(?,?,?,?)
        """,
        (
            city,
            sector,
            "Ejecutando",
            now(),
        ),
    )

    jid = cur.lastrowid

    c.commit()
    c.close()

    try:

        print(
            f"JOB ID: {jid}"
        )

        investigate(
            city,
            sector,
            jid
        )

        print(
            f"JOB {jid} TERMINADO CORRECTAMENTE"
        )

    except Exception as e:

        print("")
        print("╔" + "═" * 68 + "╗")
        print(
            "║ ERROR CRÍTICO DEL AGENTE"
            + " " * 43
            + "║"
        )
        print("╚" + "═" * 68 + "╝")

        print(
            f"JOB ID: {jid}"
        )

        print(
            f"ERROR: {str(e)}"
        )

        print("")
        print(
            "TRACEBACK COMPLETO:"
        )

        traceback.print_exc()

        print("")

        try:

            c = db()

            c.execute(
                """
                UPDATE jobs
                SET status=?,
                    error=?,
                    finished_at=?
                WHERE id=?
                """,
                (
                    "Error",
                    str(e)[:1000],
                    now(),
                    jid,
                ),
            )

            c.commit()
            c.close()

        except Exception as db_error:

            print(
                "ERROR GUARDANDO ERROR EN DB:"
            )

            print(
                str(db_error)
            )

        print(
            "EL ERROR FUE REGISTRADO EN LOS LOGS DE RENDER."
        )

    return RedirectResponse(
        "/",
        status_code=303
    )


# ============================================================
# API EMPRESAS
# ============================================================

@app.get(
    "/api/companies"
)
def companies():

    c = db()

    rows = [
        dict(x)
        for x in c.execute(
            """
            SELECT *
            FROM companies
            ORDER BY opportunity_score DESC
            """
        ).fetchall()
    ]

    c.close()

    return JSONResponse(
        rows
    )


# ============================================================
# API CONTACTOS
# ============================================================

@app.get(
    "/api/contacts"
)
def contacts():

    c = db()

    rows = [
        dict(x)
        for x in c.execute(
            """
            SELECT
                ct.*,
                co.company,
                co.city,
                co.sector,
                co.opportunity_score,
                co.priority,
                co.pain_point,
                co.recommended_service

            FROM contacts ct

            JOIN companies co
                ON co.id = ct.company_id

            WHERE ct.opt_out=0
              AND co.opt_out=0

            ORDER BY
                co.opportunity_score DESC,
                ct.priority DESC
            """
        ).fetchall()
    ]

    c.close()

    return JSONResponse(
        rows
    )


# ============================================================
# API EVIDENCIA
# ============================================================

@app.get(
    "/api/evidence/{company_id}"
)
def evidence(
    company_id: int
):

    c = db()

    rows = [
        dict(x)
        for x in c.execute(
            """
            SELECT *
            FROM evidence
            WHERE company_id=?
            ORDER BY id DESC
            """,
            (
                company_id,
            ),
        ).fetchall()
    ]

    c.close()

    return JSONResponse(
        rows
    )


# ============================================================
# OPT-OUT
# ============================================================

@app.post(
    "/api/optout/{contact_id}"
)
def optout(
    contact_id: int
):

    c = db()

    c.execute(
        """
        UPDATE contacts
        SET opt_out=1
        WHERE id=?
        """,
        (
            contact_id,
        ),
    )

    c.commit()
    c.close()

    return {
        "ok": True
    }


# ============================================================
# EXPORTAR
# ============================================================

@app.get(
    "/api/export"
)
def export():

    c = db()

    companies = [
        dict(x)
        for x in c.execute(
            """
            SELECT *
            FROM companies
            ORDER BY opportunity_score DESC
            """
        ).fetchall()
    ]

    contacts = [
        dict(x)
        for x in c.execute(
            """
            SELECT
                ct.*,
                co.company,
                co.city,
                co.sector,
                co.opportunity_score,
                co.priority

            FROM contacts ct

            JOIN companies co
                ON co.id = ct.company_id

            WHERE ct.opt_out=0
              AND co.opt_out=0
            """
        ).fetchall()
    ]

    c.close()

    return {
        "companies":
            companies,

        "contacts":
            contacts,
    }
