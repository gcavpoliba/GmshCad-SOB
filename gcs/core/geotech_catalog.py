"""Catalogo geotecnico / geotecnico-sismico per GmshCAD-SOB.

Le definizioni sono pensate per i workflow OpenSees di meccanica dei terreni,
effective-stress site response, liquefazione, consolidazione, interfacce e
interazione terreno-struttura. I campi riprendono le firme Tcl documentate
da OpenSees; gli elementi u-p esplicitano anche ndm/ndf e DOF di pressione.
"""

from __future__ import annotations
from typing import Dict, List


GEOTECH_ND_MATERIALS: Dict[str, dict] = {
    "PressureDependMultiYield02": {
        "cmd": "PressureDependMultiYield02", "family": "soil-cyclic", "ndm": (2, 3),
        "params": [
            ("nd", "int", 2, "Dimensione: 2 plane-strain / 3D"),
            ("rho", "float", 1.8, "Massa volumica"),
            ("refShearModul", "float", 7.0e4, "Modulo di taglio di riferimento"),
            ("refBulkModul", "float", 1.4e5, "Modulo di bulk di riferimento"),
            ("frictionAng", "float", 30.0, "Angolo di attrito [deg]"),
            ("peakShearStra", "float", 0.1, "Deformazione di taglio di picco"),
            ("refPress", "float", 80.0, "Pressione di riferimento"),
            ("pressDependCoe", "float", 0.5, "Coefficiente dipendenza dalla pressione"),
            ("PTAng", "float", 26.0, "Angolo di transizione di fase [deg]"),
            ("contrac1", "float", 0.067, "Contrazione ciclica c1"),
            ("contrac3", "float", 0.23, "Contrazione ciclica c3"),
            ("dilat1", "float", 0.06, "Dilatazione ciclica d1"),
            ("dilat3", "float", 0.27, "Dilatazione ciclica d3"),
        ],
        "notes": "Modello pressure-dependent per analisi sismiche ed effective stress.",
        "stage_update": True,
    },
    "PressureDependMultiYield03": {
        "cmd": "PressureDependMultiYield03", "family": "soil-cyclic", "ndm": (2, 3),
        "params": [
            ("nd", "int", 2, "Dimensione"),
            ("rho", "float", 1.8, "Massa volumica"),
            ("refShearModul", "float", 7.0e4, "Modulo di taglio di riferimento"),
            ("refBulkModul", "float", 1.4e5, "Modulo di bulk di riferimento"),
            ("frictionAng", "float", 30.0, "Angolo di attrito [deg]"),
            ("peakShearStra", "float", 0.1, "Deformazione di taglio di picco"),
            ("refPress", "float", 80.0, "Pressione di riferimento"),
            ("pressDependCoe", "float", 0.5, "Dipendenza dalla pressione"),
            ("phaseTransformAngle", "float", 26.0, "Phase transformation angle"),
            ("mType", "int", 0, "Tipo di hardening"),
            ("ca", "float", 0.0, "Parametro ca"),
            ("cb", "float", 0.0, "Parametro cb"),
            ("cc", "float", 0.0, "Parametro cc"),
            ("cd", "float", 0.0, "Parametro cd"),
            ("ce", "float", 0.0, "Parametro ce"),
            ("da", "float", 0.0, "Parametro da"),
            ("db", "float", 0.0, "Parametro db"),
            ("dc", "float", 0.0, "Parametro dc"),
            ("numberOfYieldSurf", "int", 20, "Numero superfici di snervamento"),
            ("liquefactionParam1", "float", 1.0, "Parametro liquefazione 1"),
            ("liquefactionParam2", "float", 0.0, "Parametro liquefazione 2"),
            ("atmosphericPressure", "float", 101.0, "Pressione atmosferica"),
            ("cohesi", "float", 1.73, "Coesione"),
        ],
        "notes": "Firma Tcl completa: 18 parametri obbligatori + 5 opzionali.",
        "stage_update": True,
    },
    "PM4Sand": {
        "cmd": "PM4Sand", "family": "soil-cyclic", "ndm": 2,
        "params": [
            ("Dr", "float", 0.61, "Densità relativa [0..1]"),
            ("G0", "float", 585.0, "Costante modulo di taglio"),
            ("hpo", "float", 0.28, "Parametro contrazione"),
            ("Den", "float", 0.0, "Massa volumica"),
        ],
        "notes": "Modello ciclico per sabbie; i parametri secondari possono essere lasciati ai default OpenSees.",
        "stage_update": True,
    },
    "PM4Silt": {
        "cmd": "PM4Silt", "family": "soil-cyclic", "ndm": 2,
        "params": [
            ("Su", "float", 44.0, "Resistenza al taglio non drenata"),
            ("Su_Rat", "float", -1.0, "Rapporto Su; usare -1 per il default"),
            ("G_o", "float", 585.0, "Costante modulo di taglio"),
            ("h_po", "float", 100.0, "Parametro di contrazione"),
            ("Den", "float", 0.0, "Massa volumica"),
        ],
        "notes": "PM4Silt; parametri secondari opzionali lasciati al default.",
        "stage_update": True,
    },
    "ManzariDafalias": {
        "cmd": "ManzariDafalias", "family": "soil-cyclic", "ndm": 3,
        "params": [
            ("G0", "float", 82.35, "Costante G0"),
            ("nu", "float", 0.33, "Poisson"),
            ("e_init", "float", 0.60, "Indice dei vuoti iniziale"),
            ("Mc", "float", 1.35, "Critical state stress ratio"),
            ("c", "float", 0.7, "Parametro c"),
            ("lambda_c", "float", 0.055, "Lambda_c"),
            ("e0", "float", 0.8, "e0"),
            ("ksi", "float", 0.5, "ksi"),
            ("P_atm", "float", 101.3, "Pressione atmosferica"),
            ("m", "float", 0.02, "Parametro m"),
            ("h0", "float", 16.18, "h0"),
            ("ch", "float", 0.996, "ch"),
            ("nb", "float", 0.64, "nb"),
            ("A0", "float", 0.75, "A0"),
            ("nd", "float", 1.5, "nd"),
            ("z_max", "float", 12.5, "z_max"),
            ("cz", "float", 500.0, "cz"),
            ("Den", "float", 0.0, "Densità opzionale"),
        ],
        "notes": "Critical-state cyclic soil model; usato anche nei benchmark sismici PM4Sand.",
    },
    "J2CyclicBoundingSurface": {
        "cmd": "J2CyclicBoundingSurface", "family": "soil-cyclic", "ndm": 3,
        "params": [
            ("G", "float", 8.0e4, "Modulo di taglio"),
            ("K", "float", 1.6e5, "Modulo di bulk"),
            ("Su", "float", 100.0, "Resistenza al taglio"),
            ("Den", "float", 0.0, "Massa volumica"),
            ("h", "float", 0.0, "Hardening"),
            ("m", "float", 0.0, "Parametro m"),
            ("h0", "float", 0.0, "Parametro h0"),
            ("chi", "float", 0.0, "Parametro chi"),
            ("beta", "float", 0.0, "Parametro beta"),
        ],
        "notes": "J2 cyclic bounding-surface plasticity.",
    },
    "FluidSolidPorousMaterial": {
        "cmd": "FluidSolidPorousMaterial", "family": "porous-fluid", "ndm": (2, 3),
        "params": [
            ("nd", "int", 2, "Dimensione: 2 plane-strain / 3D"),
            ("soilMatTag", "int", 1, "Tag del materiale solido"),
            ("combinedBulkModul", "float", 2.2e6, "Bulk combinato fluido-solido"),
            ("pa", "float", 101.0, "Pressione atmosferica"),
        ],
        "notes": "Accoppia fase solida e fluida; adatto a mezzi porosi saturi.",
    },
}


GEOTECH_UNIAXIAL: Dict[str, dict] = {
    "PyLiq1": {
        "cmd": "PyLiq1", "family": "pile-liquefaction", "ndm": (2, 3),
        "params": [
            ("soilType", "int", 1, "Tipo di terreno (1/2)"),
            ("pult", "float", 1.0e5, "Capacità ultima p-y"),
            ("Y50", "float", 0.01, "Spostamento al 50%"),
            ("dragratio", "float", 0.0, "Rapporto di drag"),
            ("dashpot", "float", 0.0, "Dashpot"),
            ("pRes", "float", 0.0, "Pressione residua"),
            ("solidElem1", "int", 1, "Primo elemento soil"),
            ("solidElem2", "int", 2, "Secondo elemento soil"),
        ],
        "notes": "Versione accoppiata a due elementi soil; variante -timeSeries disponibile.",
    },
    "TzLiq1": {
        "cmd": "TzLiq1", "family": "pile-liquefaction", "ndm": (2, 3),
        "params": [
            ("tzType", "int", 1, "Tipo di terreno (1/2)"),
            ("tult", "float", 1.0e5, "Capacità ultima t-z"),
            ("z50", "float", 0.01, "Spostamento al 50%"),
            ("dashpot", "float", 0.0, "Dashpot"),
            ("solidElem1", "int", 1, "Primo elemento soil"),
            ("solidElem2", "int", 2, "Secondo elemento soil"),
        ],
        "notes": "Versione accoppiata a due elementi soil; variante -timeSeries disponibile.",
    },
    "QzLiq1": {
        "cmd": "QzLiq1", "family": "pile-liquefaction", "ndm": (2, 3),
        "params": [
            ("soilType", "int", 1, "Tipo di terreno (1/2)"),
            ("qult", "float", 1.0e6, "Capacità ultima q-z"),
            ("z50", "float", 0.01, "Spostamento al 50%"),
            ("suction", "float", 0.0, "Suction"),
            ("dashpot", "float", 0.0, "Dashpot"),
            ("alpha", "float", 0.0, "Alpha"),
            ("solidElem1", "int", 1, "Primo elemento soil"),
            ("solidElem2", "int", 2, "Secondo elemento soil"),
        ],
        "notes": "Versione accoppiata a due elementi soil; variante -timeSeries disponibile.",
    },
}


GEOTECH_ELEMENTS: Dict[str, dict] = {
    "quadUP": {
        "family": "u-p", "n_nodes": 4, "ndm": 2, "ndf": 3, "pressure_dof": 3,
        "mesh_types": (3,), "mat_command": "nDMaterial",
        "args": "thick matTag bulk fmass hPerm vPerm <b1 b2 t>",
        "arg_defaults": "1.0 {matTag} 2.2e6 1.0 1e-5 1e-5 0.0 0.0 0.0",
        "notes": "4-nodi u-p: 2 spostamenti + 1 pressione.",
    },
    "bbarQuadUP": {
        "family": "u-p", "n_nodes": 4, "ndm": 2, "ndf": 3, "pressure_dof": 3,
        "mesh_types": (3,), "mat_command": "nDMaterial",
        "args": "thick matTag bulk fmass hPerm vPerm <b1 b2 t>",
        "arg_defaults": "1.0 {matTag} 2.2e6 1.0 1e-5 1e-5 0.0 0.0 0.0",
        "notes": "B-Bar 4-nodi u-p.",
    },
    "9_4_QuadUP": {
        "family": "u-p", "n_nodes": 9, "ndm": 2, "ndf": 3, "pressure_dof": 3,
        "mesh_types": (10,), "mat_command": "nDMaterial",
        "args": "type matTag thick bulk fmass hPerm vPerm <b1 b2>",
        "arg_defaults": "PlaneStrain {matTag} 1.0 2.2e6 1.0 1e-5 1e-5 0.0 0.0",
        "notes": "9 nodi displacement + 4 pressure DOF: riferimento classico per effective-stress site response.",
    },
    "SSPquadUP": {
        "family": "u-p", "n_nodes": 4, "ndm": 2, "ndf": 3, "pressure_dof": 3,
        "mesh_types": (3,), "mat_command": "nDMaterial",
        "args": "matTag thick Kf Rf k1 k2 eVoid alpha <b1 b2>",
        "arg_defaults": "{matTag} 1.0 2.2e6 1.0 1e-5 1e-5 0.6 1.0 0.0 0.0",
        "notes": "Single-point stabilized u-p; usato nei benchmark PM4Sand/PM4Silt.",
    },
    "brickUP": {
        "family": "u-p", "n_nodes": 8, "ndm": 3, "ndf": 4, "pressure_dof": 4,
        "mesh_types": (5,), "mat_command": "nDMaterial",
        "args": "matTag bulk rhof permX permY permZ <b1 b2 b3>",
        "arg_defaults": "{matTag} 2.2e6 1000.0 1e-5 1e-5 1e-5 0.0 0.0 0.0",
        "notes": "8-nodi brick u-p, 3 spostamenti + pressione.",
    },
    "bbarBrickUP": {
        "family": "u-p", "n_nodes": 8, "ndm": 3, "ndf": 4, "pressure_dof": 4,
        "mesh_types": (5,), "mat_command": "nDMaterial",
        "args": "matTag bulk rhof permX permY permZ <b1 b2 b3> [-lumped]",
        "arg_defaults": "{matTag} 2.2e6 1000.0 1e-5 1e-5 1e-5 0.0 0.0 0.0",
        "notes": "B-Bar brick u-p; supporta anche la massa lumped.",
    },
    "20_8_BrickUP": {
        "family": "u-p", "n_nodes": 20, "ndm": 3, "ndf": 4, "pressure_dof": 4,
        "mesh_types": (17,), "mat_command": "nDMaterial",
        "args": "matTag bulk rhof permX permY permZ <b1 b2 b3>",
        "arg_defaults": "{matTag} 2.2e6 1000.0 1e-5 1e-5 1e-5 0.0 0.0 0.0",
        "notes": "Brick u-p 20 nodi (Gmsh type 17) con 8 nodi corner dotati di pressione DOF.",
    },
    "SSPbrickUP": {
        "family": "u-p", "n_nodes": 8, "ndm": 3, "ndf": 4, "pressure_dof": 4,
        "mesh_types": (5,), "mat_command": "nDMaterial",
        "args": "matTag Kf Rf k1 k2 k3 eVoid alpha <b1 b2 b3> [-lumped]",
        "arg_defaults": "{matTag} 2.2e6 1000.0 1e-5 1e-5 1e-5 0.6 1.0 0.0 0.0 0.0",
        "notes": "Stabilized single-point 3D u-p brick.",
    },
    "SimpleContact2D": {
        "family": "contact-geotech", "n_nodes": 4, "ndm": 2, "ndf": 2,
        "args": "iNode jNode secondaryNode lambdaNode matTag tolGap tolForce",
        "notes": "Contatto semplice 2D nodo-superficie.",
    },
    "SimpleContact3D": {
        "family": "contact-geotech", "n_nodes": 6, "ndm": 3, "ndf": 3,
        "args": "node1 node2 node3 node4 secondaryNode lambdaNode matTag tolGap tolForce",
        "notes": "Contatto semplice 3D.",
    },
    "BeamContact2D": {
        "family": "contact-geotech", "n_nodes": 4, "ndm": 2, "ndf": 2,
        "args": "iNode jNode cNode lNode matTag width gTol fTol <cFlag>",
        "notes": "Contatto trave-terreno 2D.",
    },
    "BeamContact3D": {
        "family": "contact-geotech", "n_nodes": 5, "ndm": 3, "ndf": 3,
        "args": "iNode jNode cNode lNode matTag width gTol fTol <cFlag>",
        "notes": "Contatto trave-terreno 3D.",
    },
    "BeamEndContact3D": {
        "family": "contact-geotech", "n_nodes": 5, "ndm": 3, "ndf": 3,
        "args": "iNode jNode cNode lNode matTag width gTol fTol <cFlag>",
        "notes": "Contatto all'estremità della trave in 3D.",
    },
}


def geotech_element_options(gmsh_type: int) -> List[str]:
    """Comandi u-p direttamente compatibili con un tipo Gmsh."""
    return [name for name, info in GEOTECH_ELEMENTS.items()
            if gmsh_type in info.get("mesh_types", ())]


def is_up_element(name: str) -> bool:
    return name in GEOTECH_ELEMENTS and GEOTECH_ELEMENTS[name].get("family") == "u-p"
