"""`studymap ingest`: extract every source into _studymap/corpus/, cached by file hash.

Per-source extraction (the slow part) runs only for new or changed files, in parallel processes.
Cross-source views (near-duplicates, text/*.md, index.json) are recomputed every run but written
only when their content changes.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..course import OUT_DIR, load_config, parse_paper_name
from ..manifest import Manifest, SourceEntry, digest, sha256_file, write_atomic, write_if_changed
from .dedupe import find_duplicates
from .records import SourceRecord
from .views import source_md
from .walk import Candidate, make_sids, walk

# bump a number to re-extract every source of that type on the next run
EXTRACTOR = {"pdf": 3, "pptx": 4, "docx": 3, "text": 2, "code": 1, "image": 2}
HEAVY = {"pdf", "pptx", "docx", "image"}
SAVE_EVERY = 2.0        # seconds between manifest saves while extracting


@dataclass
class IngestResult:
    corpus: Path
    found: int = 0
    extracted: list[str] = field(default_factory=list)
    cached: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    views_written: int = 0
    resumed: bool = False
    seconds: float = 0.0
    stats: dict = field(default_factory=dict)
    papers: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def run_job(job: dict) -> dict:
    """Extract one source and write sources/<sid>.json. Runs in a worker process; never raises."""
    from .office import extract_docx, extract_pptx
    from .pdf import extract_pdf
    from .text import extract_code, extract_image, extract_text
    corpus, sid, rel, kind, typ = Path(job["corpus"]), job["sid"], job["rel"], job["kind"], job["type"]
    path = Path(job["path"])
    img_dir, img_rel = corpus / "img" / sid, f"img/{sid}"
    shutil.rmtree(img_dir, ignore_errors=True)
    try:
        if typ == "pdf":
            units, meta, warns = extract_pdf(path, rel, kind, img_dir, img_rel)
        elif typ == "pptx":
            units, meta, warns = extract_pptx(path, rel, kind, img_dir, img_rel)
        elif typ == "docx":
            units, meta, warns = extract_docx(path, rel, kind, img_dir, img_rel)
        elif typ == "image":
            units, meta, warns = extract_image(path, rel, kind, img_dir, img_rel)
        elif typ == "text":
            units, meta, warns = extract_text(path, rel, kind, job["lang"])
        else:
            units, meta, warns = extract_code(path, rel, kind, job["lang"])
    except Exception as e:  # a broken file must not stop the run
        shutil.rmtree(img_dir, ignore_errors=True)
        msg = str(e).strip().splitlines()
        return {"rel": rel, "error": f"{type(e).__name__}: {msg[0] if msg else ''}"}
    rec = SourceRecord(sid=sid, path=rel, kind=kind, type=typ, sha256=job["sha256"], extractor=job["extractor"],
                       meta=meta, warnings=warns, units=units)
    write_atomic(corpus / "sources" / f"{sid}.json", rec.model_dump_json(indent=1) + "\n")
    outputs = [f"corpus/sources/{sid}.json"]
    if img_dir.exists():
        outputs.append(f"corpus/img/{sid}/")
    return {"rel": rel, "units": len(units), "outputs": outputs, "error": None}


def _remove_outputs(out: Path, entry: SourceEntry) -> None:
    for o in entry.outputs:
        p = out / o
        if o.endswith("/"):
            shutil.rmtree(p, ignore_errors=True)
        else:
            p.unlink(missing_ok=True)


def ingest(course: Path, jobs: int = 0, force: bool = False, rehash: bool = False,
           log: Callable[[str], None] = print) -> IngestResult:
    t0 = time.monotonic()
    root = course.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"{course}: not a folder")
    cfg = load_config(root)
    out = root / OUT_DIR
    corpus = out / "corpus"
    for d in ("sources", "text", "img", "summaries"):
        (corpus / d).mkdir(parents=True, exist_ok=True)
    man_path = out / "state.json"
    man = Manifest.load(man_path)
    res = IngestResult(corpus=corpus)
    res.resumed = man.begin("ingest")
    man.save(man_path)

    found, res.skipped = walk(root, cfg.ignore)
    res.found = len(found)
    sids = make_sids([c.rel for c in found])
    current = {c.rel for c in found}
    for rel in sorted(set(man.sources) - current):
        _remove_outputs(out, man.sources.pop(rel))
        res.removed.append(rel)

    todo: list[tuple[Candidate, dict]] = []
    hashes: dict[str, str] = {}
    for c in found:
        st = c.path.stat()
        prev = man.sources.get(c.rel)
        if prev and not rehash and prev.size == st.st_size and prev.mtime_ns == st.st_mtime_ns:
            sha = prev.sha256
        else:
            sha = sha256_file(c.path)
        hashes[c.rel] = sha
        ext = f"{c.type}/{EXTRACTOR[c.type]}"
        sid = sids[c.rel]
        if (not force and prev and prev.sha256 == sha and prev.extractor == ext and prev.sid == sid
                and (corpus / "sources" / f"{sid}.json").exists()):
            prev.size, prev.mtime_ns = st.st_size, st.st_mtime_ns
            res.cached.append(c.rel)
            continue
        if prev:
            _remove_outputs(out, prev)
        man.sources.pop(c.rel, None)
        todo.append((c, dict(corpus=str(corpus), sid=sid, rel=c.rel, kind=c.kind, type=c.type, lang=c.lang,
                             path=str(c.path), sha256=sha, extractor=ext, size=st.st_size, mtime_ns=st.st_mtime_ns)))

    if todo:
        log(f"extracting {len(todo)} of {len(found)} sources" + (" (resuming an interrupted run)" if res.resumed else ""))
    last_save = time.monotonic()

    def done(job: dict, r: dict) -> None:
        nonlocal last_save
        if r["error"]:
            res.failed.append((job["rel"], r["error"]))
            log(f"  failed  {job['rel']}: {r['error']}")
            return
        man.sources[job["rel"]] = SourceEntry(sid=job["sid"], kind=job["kind"], type=job["type"], sha256=job["sha256"],
                                              size=job["size"], mtime_ns=job["mtime_ns"], extractor=job["extractor"],
                                              units=r["units"], outputs=r["outputs"])
        res.extracted.append(job["rel"])
        if job["type"] in HEAVY:
            log(f"  {job['rel']}  ({r['units']} units)")
        if time.monotonic() - last_save > SAVE_EVERY:
            man.save(man_path)
            last_save = time.monotonic()

    heavy = [j for c, j in todo if c.type in HEAVY]
    light = [j for c, j in todo if c.type not in HEAVY]
    workers = jobs or min(4, os.cpu_count() or 1)
    try:
        if workers > 1 and len(heavy) > 1:
            with ProcessPoolExecutor(max_workers=min(workers, len(heavy))) as pool:
                futs = {pool.submit(run_job, j): j for j in heavy}
                for light_job in light:          # cheap files run here while the pool works
                    done(light_job, run_job(light_job))
                for f in as_completed(futs):
                    done(futs[f], f.result())
        else:
            for j in heavy + light:
                done(j, run_job(j))
    finally:
        man.save(man_path)   # on Ctrl-C too: finished sources stay done and the next run resumes

    res.views_written, res.stats, res.papers, res.warnings = _views(root, corpus, man, res, cfg)
    res.extracted.sort()
    res.seconds = time.monotonic() - t0
    man.finish("ingest", inputs=digest(hashes), ok=not res.failed, extracted=len(res.extracted),
               cached=len(res.cached), removed=len(res.removed), failed=len(res.failed), **res.stats)
    man.save(man_path)
    return res


def _views(root: Path, corpus: Path, man: Manifest, res: IngestResult, cfg) -> tuple[int, dict, list[dict], list[str]]:
    recs: list[SourceRecord] = []
    for rel in sorted(man.sources):
        p = corpus / "sources" / f"{man.sources[rel].sid}.json"
        recs.append(SourceRecord.model_validate_json(p.read_text(encoding="utf-8")))
    dups = find_duplicates([(u.ref, r.kind, u.text) for r in recs for u in r.units])

    # papers and their answer keys, matched by name
    papers: dict[str, dict] = {}
    for r in recs:
        if r.kind != "papers":
            continue
        pn = parse_paper_name(Path(r.path).stem)
        papers[r.path] = dict(path=r.path, base=pn.base, year=pn.year, exam=pn.exam, variant=pn.variant,
                              is_key=pn.is_key, key=None, key_for=None)
    by_base = {p["base"]: p for p in papers.values() if not p["is_key"]}
    warnings = []
    for p in papers.values():
        if p["is_key"]:
            q = by_base.get(p["base"])
            if q:
                p["key_for"], q["key"] = q["path"], p["path"]
            else:
                warnings.append(f"{p['path']}: answer key with no matching paper (expected papers/{p['base']}.pdf)")

    written = 0
    keep = set()
    sources_out = []
    figs = Counter()
    flags = Counter()
    for r in recs:
        name = f"{r.sid}.md"
        keep.add(name)
        written += write_if_changed(corpus / "text" / name, source_md(r, dups, papers.get(r.path)))
        for u in r.units:
            for f in u.figures:
                figs[f.why] += 1
            for fl in u.flags:
                flags[fl] += 1
        for w in r.warnings:
            warnings.append(f"{r.path}: {w}")
        sources_out.append(dict(
            sid=r.sid, path=r.path, kind=r.kind, type=r.type, units=len(r.units),
            chars=sum(u.chars for u in r.units), images=sum(len(u.figures) for u in r.units),
            duplicates=sum(u.ref in dups for u in r.units), text=f"text/{name}",
            **({"lang": r.meta["lang"]} if r.type == "code" and r.meta.get("lang") else {}),
            **({"paper": {k: papers[r.path][k] for k in ("year", "exam", "variant", "is_key", "key", "key_for")}}
               if r.path in papers else {})))
    for f in (corpus / "text").glob("*.md"):
        if f.name not in keep:
            f.unlink()
            written += 1
    kinds = Counter(r.kind for r in recs)
    stats = dict(sources=len(recs), by_kind=dict(sorted(kinds.items())),
                 by_type=dict(sorted(Counter(r.type for r in recs).items())),
                 units=sum(len(r.units) for r in recs), images=dict(sorted(figs.items())),
                 image_only=flags["image-only"], low_text=flags["low-text"], duplicates=len(dups))
    index = dict(schema_version=1, course=dict(name=cfg.name, code=cfg.code), stats=stats,
                 papers=sorted((p for p in papers.values()), key=lambda p: p["path"]),
                 sources=sources_out, failed=[dict(path=a, error=b) for a, b in res.failed],
                 skipped=[dict(path=a, reason=b) for a, b in res.skipped], warnings=warnings)
    written += write_if_changed(corpus / "index.json", json.dumps(index, indent=1, ensure_ascii=False) + "\n")
    written += write_if_changed(corpus / "dedupe.json", json.dumps(dups, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
    return written, stats, index["papers"], warnings
