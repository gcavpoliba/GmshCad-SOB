"""Comandi utente personalizzati
==============================

Oltre alle macro, qui puoi definire **comandi rapidi** (funzioni Python
semplici) che appaiono nella console dopo l'avvio dell'app.

Esempio d'uso dalla console:

    >>> azzeramento_z()

Il dizionario ``COMMANDS`` viene letto all'avvio da main_window e iniettato
nella console; puoi aggiungere nuove funzioni liberamente.
"""

# ----------------------------------------------------------------- funzioni

def azzeramento_z(doc):
    """Esempio: riporta sul piano Z=0 l'entità selezionata più alta."""
    from gcs.core import occ_utils as ou
    solidi = [e for e in doc.selected_entities() if e.shape is not None]
    if not solidi:
        print("Nessuna entità selezionata")
        return
    top = max(solidi, key=lambda e: ou.bbox_of(e.shape)[5])
    dz = -ou.bbox_of(top.shape)[5]
    from gcs.core.editors import GeometryEditor
    GeometryEditor(doc).trasla([top.id], 0, 0, dz)
    print(f"{top.name} riportato a Z=0 (dz={dz:+.3f})")


def conteggio_tipi(doc):
    """Stampa i conteggi delle entità per tipo."""
    for t, n in sorted(doc.counts_by_type().items()):
        print(f"{t:10s}: {n}")


def griglia_punti(doc, nx=5, ny=5, passo=10, z=0):
    """Crea una griglia di punti (utile per test e costruzioni parametriche)."""
    from gcs.core.builder import GeometryBuilder
    b = GeometryBuilder(doc)
    punti = []
    for i in range(nx):
        for j in range(ny):
            punti.append(b.punto(i * passo, j * passo, z,
                                 name=f"Griglia_{i}_{j}"))
    g = doc.groups.get_or_create("griglia_punti")
    g.member_ids.update(p.id for p in punti)
    print(f"Creata griglia {nx}x{ny} ({len(punti)} punti) nel gruppo 'griglia_punti'")
    return punti


# --------------------------------------------------------------- registro

COMMANDS = {
    "azzeramento_z": azzeramento_z,
    "conteggio_tipi": conteggio_tipi,
    "griglia_punti": griglia_punti,
}
