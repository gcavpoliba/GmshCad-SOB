"""Test dell'importatore .msh (formati ASCII 2.2 e 4.1) su file sintetici
e sui campioni reali generati con gmsh."""

import os

import pytest

from gcs.core.msh_importer import parse_msh, MshFormatError
from gcs.core.mesh import MeshModel

MSH22 = """$MeshFormat
2.2 0 8
$EndMeshFormat
$PhysicalNames
3
2 1 "superficie_bassa"
2 2 "superficie_alta"
3 10 "volume_interno"
$EndPhysicalNames
$Nodes
8
1 0 0 0
2 1 0 0
3 1 1 0
4 0 1 0
5 0 0 1
6 1 0 1
7 1 1 1
8 0 1 1
$EndNodes
$Elements
7
1 15 2 99 5 1
2 1 2 1 3 1 2
3 2 2 1 3 1 2 3
4 2 2 1 3 4 1 3
5 3 2 2 4 5 6 7 8
6 4 2 10 3 1 2 3 5
7 4 2 10 3 2 3 6 5
$EndElements
"""

MSH41 = """$MeshFormat
4.1 0 8
$EndMeshFormat
$PhysicalNames
1
2 3 "parete"
$EndPhysicalNames
$Entities
1 1 1 1
1 0 0 0 0
2 0 0 0 1 0 0 0 0 0 0
3 0 0 0 1 1 0 1 3 0
4 0 0 0 1 1 1 0 0 0 0
$EndEntities
$Nodes
4 8 1 8
0 5 0 1
1
0 0 0
2 2 0 1
2
1 0 0
2 3 0 2
3
4
0.5 0.5 0
0.6 0.5 0
3 4 0 4
5
6
7
8
0.5 0.5 0.5
0.6 0.5 0.5
0.5 0.6 0.5
0.5 0.5 0.6
$EndNodes
$Elements
4 6 1 6
0 5 15 1
1 1
1 2 1 1
2 1 2
2 3 2 2
3 1 2 3
4 1 2 4
3 4 4 2
5 1 2 3 5
6 2 3 4 5
$EndElements
"""


def _scrivi(tmp_path, nome, contenuto):
    p = os.path.join(str(tmp_path), nome)
    with open(p, "w") as fh:
        fh.write(contenuto)
    return p


def test_parse_22(tmp_path):
    path = _scrivi(tmp_path, "t22.msh", MSH22)
    model = parse_msh(path)
    assert len(model.nodes) == 8
    assert len(model.elements) == 7
    assert model.physicals[(2, 1)] == "superficie_bassa"
    assert model.physicals[(3, 10)] == "volume_interno"
    # elementi organizzati in blocchi per (dim, tag)
    assert (2, 3) in model.blocks
    blk = model.blocks[(2, 3)]
    assert blk.element_ids == [3, 4]
    assert blk.physical_tags == [1]
    # punto (type 15) in blocco dim0
    assert model.block_of_element(1) == (0, 5)
    # msh2.2: tag fisico della linea
    assert model.blocks[(1, 3)].physical_tags == [1]


def test_parse_41(tmp_path):
    path = _scrivi(tmp_path, "t41.msh", MSH41)
    model = parse_msh(path)
    assert len(model.nodes) == 8
    assert len(model.elements) == 6
    assert model.nodes[5] == (0.5, 0.5, 0.5)
    assert model.nodes[6] == (0.6, 0.5, 0.5)
    # blocchi 4.1 per entità
    assert (2, 3) in model.blocks
    assert sorted(model.blocks[(2, 3)].element_ids) == [3, 4]
    assert model.blocks[(3, 4)].element_ids == [5, 6]
    # tag fisico da $Entities
    assert model.blocks[(2, 3)].physical_tags == [3]


def test_file_binario_rifiutato(tmp_path):
    path = _scrivi(tmp_path, "bin.msh", "$MeshFormat\n4.1 1 8\n$EndMeshFormat\n")
    with pytest.raises(MshFormatError):
        parse_msh(path)


def test_selettori_mesh(tmp_path):
    path = _scrivi(tmp_path, "t22.msh", MSH22)
    model = parse_msh(path)
    # selezione box: tutti tranne il quadrilatero a z=1
    n = len(model.select_elements_in_box((0, 0, -1, 1, 1, 0.6)))
    assert n == 6
    # selezione per tipo tetraedri
    assert len(model.select_elements_by_type({4})) == 2
    # gruppi fisici
    assert len(model.select_blocks_by_physical("volume_interno")) == 2
    assert len(model.select_blocks_by_physical(1)) == 3   # linea + 2 triangoli
    # crescita per nodi condivisi dai triangoli 3,4: arriva a tetraedri
    model.select_elements_by_type({2})
    model.grow_elements("nodes")
    assert 6 in model.sel_elements and 7 in model.sel_elements
    # facce di bordo dei due tetraedri: 8 facce totali, 1 condivisa -> 6 bordo
    bordo = model.boundary_faces(model.select_elements_by_type({4}))
    assert len(bordo) == 6


def test_campioni_reali():
    """I campioni generati con gmsh, se presenti, devono essere leggibili."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for nome in ("bracket_22.msh", "bracket_41.msh"):
        path = os.path.join(root, "samples", nome)
        if not os.path.exists(path):
            pytest.skip(f"campioni non generati: {path}")
        model = parse_msh(path)
        assert len(model.nodes) > 100
        assert len(model.elements) > 200
        assert "struttura" in model.physicals.values()
        # un blocco volumetrico deve esistere
        assert any(dim == 3 for (dim, _) in model.blocks)
