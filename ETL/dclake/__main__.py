"""Command line: python -m dclake <command> [options]

init       crea carpetas y .env, y muestra qué claves y archivos faltan
status     igual que init pero sin crear nada
grid       rejilla del país (--country ESP|JPN|USA) y etiquetas de las celdas
collect    ejecuta los colectores (--only / --skip / --limit-sites)
assemble   une todo en las tablas del diccionario
report     informe de cobertura por campo y bloque
all        grid + collect + assemble + report
demo       ejecución offline con datos sintéticos (comprueba la instalación)
export     Excel legible con las tablas de unas celdas (--sites a,b,c --out archivo.xlsx)
azure-setup crea (o reutiliza) el Azure Data Lake Gen2 iniciando sesión en el navegador y
           guarda la conexión en .env (sin mostrarla)
upload     sube ELT/dataset/ y azure.extra_dirs a Azure Data Lake (credenciales en .env;
           --force, --dry-run, --workers N)
qc         control de calidad del dataset del país: claves, rangos físicos y coherencia
transcribe audio público del catálogo (ELT/audio/sources.csv) a texto con ElevenLabs Scribe
excerpts   pasajes de una transcripción para leer antes de citar (--only id [--terms "a|b"])
cite       comprueba las citas de ELT/audio/claims.csv contra las transcripciones
"""

from __future__ import annotations

import argparse
import contextlib
import shutil
import sys
import time
from pathlib import Path


def _setup(args):
    from . import geo
    from .config import load_config
    from .lake import Lake

    cfg = load_config(
        args.config,
        overrides={
            "period.start": args.start,
            "period.end": args.end,
            "paths.lake_dir": args.lake_dir,
            "project.country_iso3": args.country.upper() if args.country else None,
        },
    )
    geo.set_equal_area(cfg["project"]["crs_equal_area"])
    lake = Lake(cfg.lake, cfg.dataset, iso=cfg.iso)
    lake.log.info(
        "País %s | dataset: %s | periodo %s a %s",
        cfg.iso,
        lake.tables,
        cfg["period"]["start"],
        cfg["period"]["end"],
    )
    return cfg, lake


def pick_sites(sites, limit: int | None, ids: list[str] | None = None):
    """Subset for tests: explicit ids, or N cells taken round-robin across sample types (varied
    regions)."""
    if ids:
        return sites[sites["site_id"].isin(ids)].reset_index(drop=True)
    if not limit:
        return sites
    if "sample_type" not in sites:
        return sites.head(limit)
    order = ["foco_region", "positivo_dc", "aleatoria", "resto"]
    groups = [sites[sites["sample_type"] == t].sample(frac=1, random_state=0) for t in order]
    groups += [sites[~sites["sample_type"].isin(order)]]
    rows, i = [], 0
    while len(rows) < min(limit, len(sites)):
        for g in groups:
            if i < len(g) and len(rows) < limit:
                rows.append(g.index[i])
        i += 1
    return sites.loc[rows].reset_index(drop=True)


def cmd_status(cfg, lake, create=False):
    from .collectors import REGISTRY

    root = cfg.root
    env, example = root / ".env", root / ".env.example"
    if create and not env.exists() and example.exists():
        shutil.copy(example, env)
        lake.log.info("Creado %s: rellena tus claves ahí", env)
    lake.log.info("Claves de API:")
    for cls in REGISTRY:
        c = cls(lake, cfg)
        if c.status == "pendiente":
            continue
        miss = c.missing_requirements()
        if c.requires or miss:
            lake.log.info("  %-18s %s", c.name, "OK" if not miss else f"FALTA {miss}")
    lake.log.info("Capas manuales (en %s):", lake.manual)
    from .autolayers import layer_path

    for layer in cfg.get("manual_layers", []):
        ok = layer_path(lake, cfg, layer).exists()
        state = (
            "OK   " if ok else ("AUTO " if layer.get("auto") else "FALTA")
        )  # AUTO: se descarga sola
        lake.log.info(
            "  %-16s %s  %s", layer["name"], state, "" if ok else layer.get("download", "")
        )


def cmd_collect(cfg, lake, only=None, skip=None, limit=None, ids=None):
    from .collectors import REGISTRY

    sites = pick_sites(lake.sites(), limit, ids)
    if limit or ids:
        lake.log.info("Modo prueba: %d celdas (%s)", len(sites), ", ".join(sites["site_id"]))
    unknown = (only or set()) - {c.name for c in REGISTRY}
    if unknown:
        lake.log.warning(
            "Colectores desconocidos: %s. Disponibles: %s",
            sorted(unknown),
            [c.name for c in REGISTRY],
        )
    results = {}
    skip_cfg = set(cfg["project"].get("skip_collectors") or [])
    for cls in REGISTRY:
        if only and cls.name not in only:
            continue
        if not cls.applies(cfg):  # e.g. E-OBS only in Europe, OMIE/REE only in Spain
            continue
        if not only and not cls.run_by_default:
            lake.log.info(
                "[%s] no se ejecuta por defecto (pídelo con --only %s)", cls.name, cls.name
            )
            continue
        if not only and cls.name in skip_cfg:
            lake.log.info(
                "[%s] se salta en %s (skip_collectors en config.yaml; pídelo con --only %s)",
                cls.name,
                cfg.iso,
                cls.name,
            )
            continue
        if skip and cls.name in skip:
            continue
        c = cls(lake, cfg)
        t0 = time.time()
        try:
            ok = c(sites)
            results[c.name] = (
                "ok" if ok else ("pendiente" if c.status == "pendiente" else "omitido")
            )
        except KeyboardInterrupt:
            raise
        except Exception as e:  # one failing source must not stop the rest
            lake.log.exception("[%s] ERROR: %s", c.name, e)
            results[c.name] = f"error: {e}"
        lake.log.info("[%s] %s (%.0f s)", c.name, results[c.name], time.time() - t0)
    lake.log.info("Resumen: %s", results)
    return results


def main(argv=None):
    for stream in (
        sys.stdout,
        sys.stderr,
    ):  # Windows consoles (cp1252) cannot print every character
        with contextlib.suppress(Exception):
            stream.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(
        prog="dclake", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "command",
        choices=[
            "init",
            "status",
            "grid",
            "collect",
            "assemble",
            "report",
            "all",
            "demo",
            "export",
            "azure-setup",
            "upload",
            "qc",
            "transcribe",
            "excerpts",
            "cite",
        ],
    )
    ap.add_argument(
        "--out", help="export: archivo Excel de salida (por defecto <lake>/reports/ejemplo.xlsx)"
    )
    ap.add_argument("--config", help="ruta a config.yaml (por defecto ELT/config.yaml)")
    ap.add_argument("--terms", help="excerpts: expresión regular de los términos a buscar")
    ap.add_argument(
        "--static-only",
        action="store_true",
        help="assemble: rehace todo menos la tabla semanal (minutos en vez de la mayor parte)",
    )
    ap.add_argument("--only", help="colectores separados por comas")
    ap.add_argument("--skip", help="colectores separados por comas")
    ap.add_argument(
        "--limit-sites", type=int, help="usar solo N celdas variadas de la muestra (pruebas)"
    )
    ap.add_argument("--sites", help="site_id concretos separados por comas (pruebas)")
    ap.add_argument(
        "--start", help="inicio del periodo AAAA-MM-DD (por defecto config.yaml o DCLAKE_START)"
    )
    ap.add_argument(
        "--end", help="fin del periodo AAAA-MM-DD (por defecto config.yaml o DCLAKE_END)"
    )
    ap.add_argument(
        "--lake-dir", help="carpeta del data lake (por defecto config.yaml o DCLAKE_LAKE_DIR)"
    )
    # Merge resolution: keep both country/partition options for grid and Azure upload flags
    # added by the team when the CLI evolved in parallel.
    ap.add_argument(
        "--country",
        help="país con rejilla: ESP, JPN o USA (por defecto config.yaml o DCLAKE_COUNTRY)",
    )
    ap.add_argument(
        "--part", type=int, help="solo esta parte (franja de celdas) del país; por defecto todas"
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="upload: subir también los archivos que ya están en Azure",
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="upload: mostrar qué se subiría sin subir nada"
    )
    ap.add_argument(
        "--workers", type=int, default=4, help="upload: subidas en paralelo (por defecto 4)"
    )
    args = ap.parse_args(argv)
    only = set(args.only.split(",")) if args.only else None
    skip = set(args.skip.split(",")) if args.skip else None

    if args.command == "demo":
        from .config import DEFAULT_CONFIG
        from .demo import run_demo

        run_demo(Path(args.config).resolve().parent if args.config else DEFAULT_CONFIG.parent)
        return 0

    cfg, lake = _setup(args)
    from .collectors import REGISTRY

    if args.command in ("transcribe", "excerpts", "cite"):  # unstructured audio (speech.py)
        from . import speech

        if args.command == "transcribe":
            res = speech.transcribe_sources(cfg, lake.log, only, args.workers)
            return 1 if res["failed"] else 0
        if args.command == "cite":
            speech.cite(cfg, lake.log)
            return 0
        for sid in sorted(only or []):
            t = speech.load_transcript(cfg, sid)
            print(f"===== {sid}")
            print(speech.excerpts(t, args.terms or speech.TERMS) if t else "(sin transcripción)")
        return 0

    if args.command in ("init", "status"):
        cmd_status(cfg, lake, create=args.command == "init")
    if args.command in ("grid", "all"):
        from .grid import run_grid

        run_grid(lake, cfg)
    parts = [args.part] if args.part is not None else list(range(lake.n_parts()))
    if args.command in ("collect", "all"):
        for k in parts:
            if len(parts) > 1 or args.part is not None:
                lake.log.info("===== %s: parte %d de %d =====", cfg.iso, k + 1, lake.n_parts())
            cmd_collect(
                cfg,
                lake.with_part(k),
                only,
                skip,
                args.limit_sites,
                args.sites.split(",") if args.sites else None,
            )
    if args.command in ("assemble", "all"):
        from .assemble import assemble_safely

        assemble_safely(
            lake, cfg, parts, replace_all=args.part is None, weekly=not args.static_only
        )
    if args.command in ("report", "all", "assemble"):
        from .report import coverage_report

        coverage_report(lake, cfg, REGISTRY)
    if args.command == "qc":
        from .qc import run_qc

        run_qc(lake)
    if args.command == "azure-setup":
        from .azure_setup import azure_setup

        try:
            azure_setup(cfg, lake.log)
        except RuntimeError as e:
            lake.log.error("azure-setup: %s", e)
            return 1
    if args.command == "upload":
        from .upload import upload_dataset

        try:
            upload_dataset(lake, cfg, force=args.force, dry_run=args.dry_run, workers=args.workers)
        except RuntimeError as e:
            lake.log.error("upload: %s", e)
            return 1
    if args.command == "export":
        if not args.out:
            lake.log.error("export necesita --out <archivo.xlsx>")
            return 1
        from .export import export_sample

        export_sample(lake, cfg, args.sites.split(",") if args.sites else None, Path(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
