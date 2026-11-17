"""Command line: `omr setup`, `omr check-tools`, `omr recognize <input>`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config


def _print_status(results) -> bool:
    all_ok = True
    for r in results:
        mark = "OK " if r.ok else ("-- " if not r.required else "XX ")
        print(f"  [{mark}] {r.name:<12} {r.detail}" + (f"\n         {r.path}" if r.path else ""))
        if r.required and not r.ok:
            all_ok = False
    return all_ok


def cmd_check(args, cfg) -> int:
    from .tools import check_tools

    print("Verificando herramientas...")
    ok = _print_status(check_tools(cfg, install=args.install))
    print("Todo listo." if ok else "Faltan herramientas obligatorias (ver arriba).")
    return 0 if ok else 1


def cmd_recognize(args, cfg) -> int:
    from .pipeline import recognize

    src = Path(args.input).expanduser().resolve()
    if not src.exists():
        print(f"No existe: {src}")
        return 1
    if args.engines:
        cfg["recognition"]["engines"] = args.engines.split(",")
    if args.variants:
        cfg["preprocess"]["variants"] = args.variants.split(",")
    try:
        run_dir = recognize(src, cfg, Path(args.runs_dir), args.letra, title=args.titulo)
    except RuntimeError as e:
        print(e)
        return 1
    _validate_and_print(run_dir, cfg, open_report=not args.no_open)
    return 0


def _validate_and_print(run_dir: Path, cfg: dict, open_report: bool) -> None:
    from .pipeline import validate_run

    print("Votando y validando...")
    res = validate_run(run_dir, cfg)
    n = len(res["doubtful_measures"])
    print(f"  {len(res['readings'])} lecturas; {res['measures']} compases, {res['verses']} estrofa(s); "
          f"{n} compás(es) dudoso(s)" + (f": {', '.join(res['doubtful_measures'])}" if n else ""))
    print(f"  Partitura final (4 voces): {res['voices_xml']}")
    print(f"  Reporte: {res['report']}")
    from .evaluate import evaluate_run, find_ground_truth, summary_lines

    gt = find_ground_truth(run_dir)
    if gt:
        print(f"Evaluando contra {gt}...")
        for line in summary_lines(evaluate_run(run_dir, gt, Path(res["voices_xml"]), cfg)):
            print(line)
        print(f"  Detalle: {run_dir / 'evaluacion.html'}")
    if open_report:
        import webbrowser

        webbrowser.open(Path(res["report"]).resolve().as_uri())


def cmd_validate(args, cfg) -> int:
    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"No existe la carpeta: {run_dir}")
        return 1
    _validate_and_print(run_dir, cfg, open_report=not args.no_open)
    return 0


def cmd_evaluate(args, cfg) -> int:
    from .evaluate import evaluate_run, find_ground_truth, summary_lines
    from .pipeline import final_file

    run_dir = Path(args.run_dir)
    gt = Path(args.correcto) if args.correcto else find_ground_truth(run_dir)
    if not gt or not gt.exists():
        print("No encuentro el MusicXML correcto: ponlo en ground_truth/ con el mismo nombre que la entrada, "
              "o indícalo con --correcto")
        return 1
    final = final_file(run_dir)
    if not final:
        print(f"No hay resultado final en {run_dir}; ejecuta antes: omr validate \"{run_dir}\"")
        return 1
    result = evaluate_run(run_dir, gt, final, cfg)
    for line in summary_lines(result):
        print(line)
    print(f"  Detalle: {run_dir / 'evaluacion.html'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="omr", description="OMR coral con autocorrección")
    parser.add_argument("--config", help="ruta a config.yaml (por defecto ./config.yaml si existe)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("setup", help="instala y verifica todas las herramientas")
    p.set_defaults(func=cmd_check, install=True)

    p = sub.add_parser("check-tools", help="verifica herramientas sin instalar nada")
    p.set_defaults(func=cmd_check, install=False)

    p = sub.add_parser("recognize", help="reconoce un PDF, imagen o carpeta de imágenes")
    p.add_argument("input")
    p.add_argument("--runs-dir", default="runs")
    p.add_argument("--engines", help="motores separados por comas (por defecto, los de config.yaml)")
    p.add_argument("--variants", help="variantes de imagen separadas por comas (por defecto, las de config.yaml)")
    p.add_argument("--letra", help="archivo .txt con la letra (por defecto, el .txt con el mismo nombre que la entrada)")
    p.add_argument("--titulo", help="nombre del himno para el archivo final (por defecto, el título leído en la imagen)")
    p.add_argument("--no-open", action="store_true", help="no abrir el reporte en el navegador")
    p.set_defaults(func=cmd_recognize)

    p = sub.add_parser("validate", help="vuelve a validar una ejecución y regenera su reporte")
    p.add_argument("run_dir", help="carpeta dentro de runs/")
    p.add_argument("--no-open", action="store_true", help="no abrir el reporte en el navegador")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("evaluate", help="compara una ejecución con un MusicXML correcto hecho a mano")
    p.add_argument("run_dir", help="carpeta dentro de runs/")
    p.add_argument("--correcto", help="MusicXML correcto (por defecto, ground_truth/<nombre de la entrada>)")
    p.set_defaults(func=cmd_evaluate)

    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    return args.func(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
