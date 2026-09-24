"""DOCX-Vorlagen befüllen und Platzhalter prüfen."""

from __future__ import annotations

import html
import re
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any

# docxtpl stellt diese Namen selbst bereit – sie sind keine fehlenden Angaben.
_DOCXTPL_BUILTINS = {
    "RichText", "R", "InlineImage", "Listing", "Subdoc",
    "BlockProtected", "MSO", "hyperlink",
}


def get_template_variables(template_path: Path) -> set[str]:
    """Alle {{ variable }}-Namen einer DOCX-Vorlage.

    XML-Tags werden vorher entfernt, damit über mehrere <w:r>-Runs verteilte
    Platzhalter wieder zusammenhängen.
    """
    variables: set[str] = set()
    with zipfile.ZipFile(str(template_path), "r") as z:
        for entry in z.namelist():
            if not entry.endswith(".xml"):
                continue
            raw = z.read(entry).decode("utf-8", errors="ignore")
            text = re.sub(r"<[^>]*>", "", raw)
            variables.update(re.findall(r"\{\{-?\s*(\w+)\s*-?\}\}", text))
    return variables - _DOCXTPL_BUILTINS


def missing_placeholders(template_path: Path, context: dict) -> list[str]:
    """Platzhalter der Vorlage, deren Wert leer wäre."""
    return sorted(v for v in get_template_variables(template_path) if context.get(v) in (None, ""))


def fill_docx(template_path: Path, context: dict, output_path: Path) -> Path:
    from docxtpl import DocxTemplate

    ctx = dict(context)
    # Zeilenumbrüche innerhalb eines Absatzes zusammenziehen; nur \n\n trennt Absätze.
    anschreiben = ctx.get("anschreiben", "")
    if isinstance(anschreiben, str) and "\n\n" in anschreiben:
        chunks = re.split(r"\n{2,}", anschreiben)
        ctx["anschreiben"] = "\n\n".join(
            " ".join(ln.strip() for ln in chunk.split("\n") if ln.strip()) for chunk in chunks
        )

    # docxtpl escaped nicht selbst; nacktes & < > würde ungültiges XML erzeugen.
    render_ctx = {
        k: html.escape(v, quote=False) if isinstance(v, str) else v for k, v in ctx.items()
    }

    tpl = DocxTemplate(str(template_path))
    tpl.render(render_ctx)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tpl.save(str(output_path))

    try:
        _fix_line_breaks(output_path)
    except Exception:
        pass  # nicht kritisch: die Datei ist auch ohne Nachbearbeitung nutzbar
    return output_path


def _fix_line_breaks(docx_path: Path) -> None:
    """Von docxtpl eingefügte <w:br/> in echte Absatzwechsel umwandeln."""
    import lxml.etree as etree
    from docx import Document
    from docx.oxml.ns import qn

    W_P, W_R, W_BR = qn("w:p"), qn("w:r"), qn("w:br")
    W_PPR, W_RPR, W_TYPE = qn("w:pPr"), qn("w:rPr"), qn("w:type")

    def is_soft_br(elem: Any) -> bool:
        return elem.tag == W_BR and elem.get(W_TYPE, "") not in ("page", "column")

    def make_run(rPr: Any, elems: list) -> Any:
        new_r = etree.Element(W_R)
        if rPr is not None:
            new_r.append(deepcopy(rPr))
        for e in elems:
            new_r.append(deepcopy(e))
        return new_r

    doc = Document(str(docx_path))
    body = doc.element.body
    modified = False

    for p_elem in list(body.iter(W_P)):
        pPr = p_elem.find(W_PPR)
        if not any(is_soft_br(c) for r in p_elem.iter(W_R) for c in r):
            continue

        segments: list[list] = [[]]
        for child in list(p_elem):
            if child.tag == W_PPR:
                continue
            if child.tag != W_R:
                segments[-1].append(deepcopy(child))
                continue
            rPr = child.find(W_RPR)
            pending: list = []
            for rc in child:
                if rc.tag == W_RPR:
                    continue
                if is_soft_br(rc):
                    if pending:
                        segments[-1].append(make_run(rPr, pending))
                        pending = []
                    segments.append([])
                else:
                    pending.append(rc)
            if pending:
                segments[-1].append(make_run(rPr, pending))

        if len(segments) <= 1:
            continue

        for child in list(p_elem):
            if child.tag != W_PPR:
                p_elem.remove(child)
        for elem in segments[0]:
            p_elem.append(elem)

        parent = p_elem.getparent()
        idx = list(parent).index(p_elem)
        for i, seg in enumerate(segments[1:], 1):
            new_p = etree.Element(W_P)
            if pPr is not None:
                new_p.append(deepcopy(pPr))
            for elem in seg:
                new_p.append(elem)
            parent.insert(idx + i, new_p)
        modified = True

    if modified:
        doc.save(str(docx_path))
