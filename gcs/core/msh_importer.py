"""Importatore di file mesh Gmsh ``.msh`` (formati ASCII 2.2 e 4.1).

Il parser è scritto a mano (nessuna dipendenza) così da controllare
integralmente la mappatura verso :class:`~gcs.core.mesh.MeshModel`:

  * ``$PhysicalNames``  -> nomi dei gruppi fisici
  * ``$Nodes``          -> nodi
  * ``$Elements``       -> elementi, organizzati in blocchi ``(dim, tag)``
  * ``$Entities`` (4.1) -> struttura entità + tag fisici

Per file **binari** o versioni non supportate usare
:func:`gcs.core.gmsh_bridge.import_msh_gmsh` (richiede il pacchetto gmsh).
"""

from __future__ import annotations

from typing import List, Optional

from .mesh import MeshModel, MeshBlock


class MshFormatError(Exception):
    """Errore di formato durante la lettura di un file .msh."""


def _open_lines(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read().splitlines()


class _Reader:
    """Iteratore di righe non vuote con supporto look-ahead."""

    def __init__(self, lines: List[str]):
        self._lines = lines
        self._i = 0

    def next_line(self) -> str:
        while self._i < len(self._lines):
            riga = self._lines[self._i].strip()
            self._i += 1
            if riga:
                return riga
        raise MshFormatError("Fine file inattesa: sezione mancante o file troncato")

    def eof(self) -> bool:
        return self._i >= len(self._lines)

    def read_section(self) -> Optional[str]:
        """Ritorna il nome della prossima sezione ($XXX) o None se EOF.

        Le righe ``$EndXXX`` sono terminatori di sezione: vengono ignorate
        qui e consumate dalle funzioni che leggono il corpo della sezione.
        """
        while True:
            if self._i >= len(self._lines):
                return None
            riga = self._lines[self._i].strip()
            self._i += 1
            if riga and riga.startswith("$") and not riga.startswith("$End"):
                return riga[1:]
        return None


def _parse_physical_names(rd: _Reader, model: MeshModel) -> None:
    n = int(rd.next_line())
    for _ in range(n):
        parts = rd.next_line().split(None, 2)
        dim, tag = int(parts[0]), int(parts[1])
        nome = parts[2].strip().strip('"').strip("'") if len(parts) > 2 else f"Phys{tag}"
        model.add_physical(dim, tag, nome)


def _parse_nodes_22(rd: _Reader, model: MeshModel) -> None:
    n = int(rd.next_line())
    for _ in range(n):
        p = rd.next_line().split()
        model.add_node(int(p[0]), float(p[1]), float(p[2]), float(p[3]))


def _parse_elements_22(rd: _Reader, model: MeshModel) -> None:
    n = int(rd.next_line())
    for _ in range(n):
        p = [int(v) for v in rd.next_line().split()]
        eid, etype, ntags = p[0], p[1], p[2]
        tags = p[3:3 + ntags]
        nodes = p[3 + ntags:]
        # tag[0]=fisico, tag[1]=tag entità geometrica (convenzione gmsh 2.2)
        fisico = tags[0] if ntags >= 1 else 0
        entita = tags[1] if ntags >= 2 else 0
        if etype == 15:
            dim = 0
        elif etype in (1, 8):
            dim = 1
        elif etype in (2, 3, 9, 10, 16):
            dim = 2
        else:
            dim = 3
        model.add_element(eid, etype, nodes, (dim, entita))
        if fisico:
            blk = model.blocks[(dim, entita)]
            if fisico not in blk.physical_tags:
                blk.physical_tags.append(fisico)


def _parse_entities_41(rd: _Reader, model: MeshModel) -> None:
    """$Entities in MSH 4.1: tag fisici per punto/curva/superficie/volume.

    Struttura righe (ASCII):
      punto:    tag x y z nPhys [phys...]
      altro:    tag xmin ymin zmin xmax ymax zmax nPhys [phys... nBnd bnd...]
    """
    counts = [int(v) for v in rd.next_line().split()]
    for dim, count in enumerate(counts):
        for _ in range(count):
            p = rd.next_line().split()
            tag = int(p[0])
            n_phys = int(p[4]) if dim == 0 else int(p[7])
            phys = [int(v) for v in p[8:8 + n_phys]] if dim > 0 else \
                [int(v) for v in p[5:5 + n_phys]]
            model.blocks.setdefault((dim, tag), MeshBlock(dim, tag))
            blk = model.blocks[(dim, tag)]
            for pt in phys:
                if pt not in blk.physical_tags:
                    blk.physical_tags.append(pt)


def _parse_nodes_41(rd: _Reader, model: MeshModel) -> None:
    header = rd.next_line().split()
    n_blocchi = int(header[0])
    for _ in range(n_blocchi):
        bd = rd.next_line().split()          # entityDim entityTag parametric nNodi
        n_nodi = int(bd[3])
        tags = [int(rd.next_line()) for _ in range(n_nodi)]
        for t in tags:
            p = rd.next_line().split()
            model.add_node(t, float(p[0]), float(p[1]), float(p[2]))


def _parse_elements_41(rd: _Reader, model: MeshModel) -> None:
    header = rd.next_line().split()
    n_blocchi = int(header[0])
    for _ in range(n_blocchi):
        bd = rd.next_line().split()          # entityDim entityTag elementType nElementi
        dim, tag, etype = int(bd[0]), int(bd[1]), int(bd[2])
        n_el = int(bd[3])
        info_nodes = _nnodi(etype)
        for _ in range(n_el):
            p = [int(v) for v in rd.next_line().split()]
            eid = p[0]
            nodes = p[1:1 + info_nodes]
            model.add_element(eid, etype, nodes, (dim, tag))


def _nnodi(etype: int) -> int:
    from .mesh import ELEM_INFO
    info = ELEM_INFO.get(etype)
    if info and info[1]:
        return info[1]
    # tipi sconosciuti: deduci dalla lunghezza della riga chiamante (fallback)
    raise MshFormatError(f"Tipo elemento gmsh {etype} non in tabella")


def parse_msh(path: str) -> MeshModel:
    """Legge un file ``.msh`` ASCII (2.2 o 4.1) e restituisce il MeshModel."""
    lines = _open_lines(path)
    if not lines:
        raise MshFormatError(f"File vuoto: {path}")

    # rileva versione e formato (ASCII/binario)
    versione, binario = None, False
    for i, ln in enumerate(lines[:50]):
        if ln.strip().startswith("$MeshFormat"):
            if i + 1 >= len(lines):
                raise MshFormatError("Sezione $MeshFormat incompleta")
            parti = lines[i + 1].split()
            versione, binario = parti[0], (len(parti) > 1 and parti[1] == "1")
            break
    if versione is None:
        raise MshFormatError("Sezione $MeshFormat non trovata")
    if binario:
        raise MshFormatError(
            f"File MSH {versione} BINARIO: non supportato dal parser ASCII. "
            f"Usare gcs.core.gmsh_bridge.import_msh_gmsh()")

    if versione.startswith("2."):
        return _parse_v2(lines, versione, path)
    if versione.startswith("4."):
        return _parse_v4(lines, versione, path)
    raise MshFormatError(
        f"Versione MSH {versione} non supportata dal parser ASCII "
        f"(supportate 2.2 e 4.1; per binario usare gmsh_bridge)")


def _parse_v2(lines: List[str], versione: str, path: str) -> MeshModel:
    model = MeshModel(f"msh{versione}", path)
    rd = _Reader(lines)
    while True:
        sez = rd.read_section()
        if sez is None:
            break
        if sez == "MeshFormat":
            _skip_section(rd)
        elif sez == "PhysicalNames":
            _parse_physical_names(rd, model)
        elif sez == "Nodes":
            _parse_nodes_22(rd, model)
        elif sez == "Elements":
            _parse_elements_22(rd, model)
        else:
            _skip_section(rd)
    return model


def _parse_v4(lines: List[str], versione: str, path: str) -> MeshModel:
    model = MeshModel(f"msh{versione}", path)
    rd = _Reader(lines)
    while True:
        sez = rd.read_section()
        if sez is None:
            break
        if sez in ("MeshFormat", "Periodic", "PartitionedEntities", "GhostElements",
                   "NodeData", "ElementData", "ElementNodeData"):
            _skip_section(rd)
        elif sez == "PhysicalNames":
            _parse_physical_names(rd, model)
        elif sez == "Entities":
            _parse_entities_41(rd, model)
        elif sez == "Nodes":
            _parse_nodes_41(rd, model)
        elif sez == "Elements":
            _parse_elements_41(rd, model)
        else:
            _skip_section(rd)
    return model


def _skip_section(rd: _Reader) -> None:
    """Salta le righe fino a $EndXXX."""
    while True:
        riga = rd.next_line()
        if riga.startswith("$End"):
            return
