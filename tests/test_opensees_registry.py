from gcs.core.opensees_registry import (
    OFFICIAL_MANUAL,
    OFFICIAL_REPO,
    OpenSeesCommandRegistry,
)


def test_registry_has_core_commands_and_catalogs():
    reg = OpenSeesCommandRegistry()
    names = {row.name for row in reg.all()}
    assert "node" in names
    assert "element" in names
    assert "nDMaterial" in names
    assert "updateParameter" in names
    assert "updateMaterials" in names
    assert "updateMaterialStage" in names
    assert "block2D" in names
    assert "block3D" in names
    assert "fixX" in names
    assert "generateInterfacePoints" in names
    assert "nodalLoad" in names
    assert len(names) > 100


def test_registry_filters_and_exposes_source():
    reg = OpenSeesCommandRegistry()
    rows = reg.find("PressureDependMultiYield", kind="nDMaterial")
    assert rows
    row = rows[0]
    assert row.name == "PressureDependMultiYield"
    assert row.source.startswith("SRC/")
    assert row.source_url.startswith(OFFICIAL_REPO + "/tree/master/")
    assert row.documentation == OFFICIAL_MANUAL
    assert row.schema is not None


def test_registry_coverage_is_stable_shape():
    coverage = OpenSeesCommandRegistry().coverage()
    assert coverage["total"] >= coverage["implemented"] > 0
    assert "by_kind" in coverage
    assert coverage["official_repo"] == OFFICIAL_REPO
