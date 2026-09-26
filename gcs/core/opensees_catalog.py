"""Catalogo completo dei comandi di modellazione OpenSees.

Questo modulo contiene tutte le tabelle di catalogo (materiali, elementi,
sezioni, geomTransf, timeSeries, pattern, solutori, recorder, ecc.)
estratte dal repository OpenSees (SRC/runtime/commands/ e SRC/modelbuilder/tcl/).

Le tabelle sono usate da `opensees_conditions.py` per validare le definizioni
utente, dalla GUI per popolare i dialog di creazione e da `opensees_export.py`
per emettere il codice Tcl corretto.

Convenzione: ogni voce di catalogo è una dict con chiavi:
- `cmd`      : nome del comando Tcl (es. "Steel01")
- `family`   : famiglia (es. "steel", "concrete", "elastic", "soil", ...)
- `ndm`       : dimensione del modello (1, 2, 3) o None = qualsiasi
- `params`   : lista di tuple (nome, tipo, default, descrizione)
              tipo ∈ {"float", "int", "bool", "str", "vec3", "choice:opt1|opt2"}
- `alias`    : lista di alias Tcl (opzionale)
- `notes`    : nota testuale (opzionale)
- `extra`    : eventuali flag opzionali speciali
"""

from __future__ import annotations
from typing import Dict, List, Tuple, Any


# =============================================================================
# 1. UNIAXIAL MATERIALS (uniaxialMaterial) - catalogo completo
# =============================================================================

UNIAXIAL_MATERIALS: Dict[str, dict] = {
    # --- Elastici / base ---
    "Elastic": {
        "cmd": "Elastic", "family": "elastic", "ndm": None,
        "params": [("E", "float", 2.0e11, "Modulo elastico [N/m^2]"),
                   ("eta", "float", 0.0, "Coefficiente di smorzamento viscoso (opzionale)")],
        "extra": {"eta_optional": True},
    },
    "ElasticPP": {
        "cmd": "ElasticPP", "family": "elastic", "ndm": None,
        "params": [("E", "float", 2.0e11, "Modulo elastico"),
                   ("epsy", "float", 0.002, "Deformazione di snervamento"),
                   ("eps0", "float", 0.0, "Deformazione iniziale (opzionale)")],
        "extra": {"eps0_optional": True},
    },
    "ElasticPPGap": {
        "cmd": "ElasticPPGap", "family": "elastic", "ndm": None,
        "params": [("E", "float", 2.0e11, "Modulo elastico"),
                   ("Fy", "float", 3.0e5, "Forza di snervamento"),
                   ("gap", "float", 0.0, "Gap iniziale (positivo o negativo)"),
                   ("eta", "float", 0.0, "Smorzamento (opzionale, default 0)")],
    },
    "ENT": {
        "cmd": "ENT", "family": "elastic", "ndm": None,
        "params": [("E", "float", 2.0e11, "Modulo elastico")],
    },
    "ElasticBilin": {
        "cmd": "ElasticBilin", "family": "elastic", "ndm": None,
        "params": [("E1", "float", 1.0e11, "Modulo primo ramo"),
                   ("E2", "float", 1.0e10, "Modulo secondo ramo"),
                   ("epsy", "float", 0.002, "Deformazione di transizione")],
    },
    "ElasticMultiLinear": {
        "cmd": "ElasticMultiLinear", "family": "elastic", "ndm": None,
        "params": [("-strain", "vec3", "0,0.002,1", "Deformazioni ai punti"),
                   ("-stress", "vec3", "0,4e8,4e8", "Tensioni ai punti")],
    },
    "Hardening": {
        "cmd": "Hardening", "family": "plastic", "ndm": None,
        "params": [("E", "float", 2.0e11, "Modulo elastico"),
                   ("H", "float", 1.0e10, "Modulo plastico isotropo"),
                   ("b", "float", 0.0, "Modulo plastico cinematico"),
                   ("a", "float", 0.0, "Spostamento della soglia (opzionale)")],
    },
    "Parallel": {
        "cmd": "Parallel", "family": "composite", "ndm": None,
        "params": [("-mat", "str", "1 2", "Tags materiali in parallelo (separati da spazio)"),
                   ("-frac", "str", "", "Frazioni (opzionale, separati da spazio)")],
    },
    "Series": {
        "cmd": "Series", "family": "composite", "ndm": None,
        "params": [("-mat", "str", "1 2", "Tags materiali in serie (separati da spazio)")],
    },
    # --- Acciaio ---
    "Steel01": {
        "cmd": "Steel01", "family": "steel", "ndm": None,
        "params": [("Fy", "float", 3.45e8, "Tensione di snervamento [Pa]"),
                   ("E0", "float", 2.0e11, "Modulo elastico iniziale [Pa]"),
                   ("b", "float", 0.01, "Rapporto di indurimento (E_t/E_0)"),
                   ("a1", "float", 0.025, "Parametro isotropo 1 (default)"),
                   ("a2", "float", 1.0, "Parametro isotropo 2"),
                   ("a3", "float", 0.025, "Parametro isotropo 3"),
                   ("a4", "float", 1.0, "Parametro isotropo 4")],
        "extra": {"a_params_optional": True},
    },
    "Steel02": {
        "cmd": "Steel02", "family": "steel", "ndm": None,
        "params": [("Fy", "float", 3.45e8, "Tensione di snervamento"),
                   ("E0", "float", 2.0e11, "Modulo elastico"),
                   ("b", "float", 0.01, "Rapporto di indurimento"),
                   ("R0", "float", 15.0, "Parametro transizione (default 15)"),
                   ("cR1", "float", 0.925, "Parametro transizione 1"),
                   ("cR2", "float", 0.15, "Parametro transizione 2"),
                   ("a1", "float", 0.025, "Parametro isotropo 1"),
                   ("a2", "float", 1.0, "Parametro isotropo 2"),
                   ("a3", "float", 0.025, "Parametro isotropo 3"),
                   ("a4", "float", 1.0, "Parametro isotropo 4"),
                   ("sigInit", "float", 0.0, "Tensione iniziale (opzionale)")],
        "extra": {"optional_tail": True},
    },
    "SteelMP": {
        "cmd": "SteelMP", "family": "steel", "ndm": None,
        "params": [("Fy", "float", 3.45e8, "Tensione di snervamento"),
                   ("E0", "float", 2.0e11, "Modulo elastico"),
                   ("b", "float", 0.01, "Rapporto indurimento"),
                   ("params", "str", "", "Parametri opzionali (R0 cR1 cR2 a1 a2 a3 a4)")],
    },
    "ReinforcingSteel": {
        "cmd": "ReinforcingSteel", "family": "steel", "ndm": None,
        "params": [("fy", "float", 4.2e8, "Tensione di snervamento"),
                   ("fu", "float", 6.1e8, "Tensione ultima"),
                   ("Es", "float", 2.0e11, "Modulo elastico"),
                   ("Esh", "float", 5.0e9, "Modulo nel ramo di indurimento"),
                   ("eps_sh", "float", 0.002, "Deformazione all'inizio dell'indurimento"),
                   ("eps_ult", "float", 0.12, "Deformazione ultima"),
                   ("eps_su", "float", 0.10, "Deformazione ultima di snervamento")],
    },
    "Bond_SP01": {
        "cmd": "Bond_SP01", "family": "steel", "ndm": None,
        "params": [("Fy", "float", 3.45e8, "Tensione di snervamento"),
                   ("SU", "float", 5.0e8, "Tensione ultima"),
                   ("E0", "float", 2.0e11, "Modulo elastico"),
                   ("b", "float", 0.01, "Rapporto indurimento"),
                   ("R", "float", 1.0, "Parametro di transizione")],
    },
    # --- Calcestruzzo ---
    "Concrete01": {
        "cmd": "Concrete01", "family": "concrete", "ndm": None,
        "params": [("fpc", "float", -3.0e7, "Resistenza a compressione [Pa] (negativa)"),
                   ("epsc0", "float", -0.002, "Deformazione a fpc"),
                   ("fpcu", "float", -6.0e6, "Resistenza residua [Pa]"),
                   ("epscu", "float", -0.0035, "Deformazione a fpcu")],
    },
    "Concrete02": {
        "cmd": "Concrete02", "family": "concrete", "ndm": None,
        "params": [("fpc", "float", -3.0e7, "Resistenza a compressione"),
                   ("epsc0", "float", -0.002, "Deformazione a fpc"),
                   ("fpcu", "float", -6.0e6, "Resistenza residua"),
                   ("epscu", "float", -0.0035, "Deformazione a fpcu"),
                   ("ratio", "float", 0.1, "Rapporto Ft/Fpc per trazione"),
                   ("ft", "float", 3.0e6, "Tensione di trazione (opzionale)"),
                   ("Ets", "float", 1.0e10, "Modulo di tension-softening (opzionale)")],
    },
    "Concrete04": {
        "cmd": "Concrete04", "family": "concrete", "ndm": None,
        "params": [("fpc", "float", -3.0e7, "Resistenza a compressione"),
                   ("epsc0", "float", -0.002, "Deformazione a fpc"),
                   ("epscu", "float", -0.0035, "Deformazione ultima a compressione"),
                   ("Ec", "float", 2.4e10, "Modulo elastico"),
                   ("fct", "float", 3.0e6, "Resistenza a trazione"),
                   ("et", "float", 1.0e-4, "Deformazione a fct")],
    },
    "Concrete06": {
        "cmd": "Concrete06", "family": "concrete", "ndm": None,
        "params": [("fpc", "float", -3.0e7, "Resistenza a compressione"),
                   ("epsc0", "float", -0.002, "Deformazione a fpc"),
                   ("fpcu", "float", -6.0e6, "Resistenza residua"),
                   ("epscu", "float", -0.0035, "Deformazione a fpcu"),
                   ("r", "float", 2.0, "Esponente di Popovics"),
                   ("alpha", "float", 1.0, "Parametro di confinamento")],
    },
    "ConcreteCM": {
        "cmd": "ConcreteCM", "family": "concrete", "ndm": None,
        "params": [("fpc", "float", -3.0e7, "Resistenza a compressione"),
                   ("epsc0", "float", -0.002, "Deformazione a fpc"),
                   ("fpcu", "float", -6.0e6, "Resistenza residua"),
                   ("epscu", "float", -0.0035, "Deformazione a fpcu"),
                   ("ratio", "float", 0.1, "Rapporto Ft/Fpc"),
                   ("ft", "float", 3.0e6, "Tensione di trazione"),
                   ("Ets", "float", 1.0e10, "Modulo tension-softening"),
                   ("alpha", "float", 0.0, "Parametro alpha")],
    },
    "ConfinedConcrete01": {
        "cmd": "ConfinedConcrete01", "family": "concrete", "ndm": None,
        "params": [("fpc", "float", -3.0e7, "Resistenza confinata"),
                   ("epsc0", "float", -0.002, "Deformazione a fpc"),
                   ("fpcu", "float", -6.0e6, "Resistenza residua"),
                   ("epscu", "float", -0.0035, "Deformazione a fpcu")],
    },
    "Hysteretic": {
        "cmd": "Hysteretic", "family": "hysteretic", "ndm": None,
        "params": [("s1p", "float", 1.0e5, "Forza al punto 1 positivo"),
                   ("e1p", "float", 0.001, "Deformazione al punto 1 positivo"),
                   ("s2p", "float", 1.5e5, "Forza al punto 2 positivo"),
                   ("e2p", "float", 0.005, "Deformazione al punto 2 positivo"),
                   ("s3p", "float", 1.0e5, "Forza al punto 3 positivo"),
                   ("e3p", "float", 0.02, "Deformazione al punto 3 positivo"),
                   ("s1n", "float", -1.0e5, "Forza al punto 1 negativo (default = -s1p)"),
                   ("e1n", "float", -0.001, "Deformazione al punto 1 negativo"),
                   ("s2n", "float", -1.5e5, "Forza al punto 2 negativo"),
                   ("e2n", "float", -0.005, "Deformazione al punto 2 negativo"),
                   ("s3n", "float", -1.0e5, "Forza al punto 3 negativo"),
                   ("e3n", "float", -0.02, "Deformazione al punto 3 negativo"),
                   ("pinchX", "float", 0.5, "Fattore di pinch asse X"),
                   ("pinchY", "float", 1.0, "Fattore di pinch asse Y"),
                   ("damage1", "float", 0.0, "Danno dovuto a duttilità"),
                   ("damage2", "float", 0.0, "Danno dovuto a energia"),
                   ("beta", "float", 0.0, "Parametro di degrado")],
        "extra": {"negative_optional": True},
    },
    "Pinching4": {
        "cmd": "Pinching4", "family": "hysteretic", "ndm": None,
        "params": [("-ePf1", "str", "0 5e5", "Coppie [deformazione, forza] - ramo positivo (4 punti)"),
                   ("relDegrad", "str", "0.5 0.5 0.5 0.5 0.5 0.5 0.5 0.5 0.5", "Parametri di degrado"),
                   ("forceFunc", "str", "1 1 1 1 1 1 1 1 1", "Funzioni forza")],
    },
    "Bilin": {
        "cmd": "Bilin", "family": "hysteretic", "ndm": None,
        "params": [("ke", "float", 1.0e8, "Rigidità elastica"),
                   ("My_pos", "float", 1.0e5, "Momento di snervamento positivo"),
                   ("My_neg", "float", -1.0e5, "Momento di snervamento negativo"),
                   ("Ls", "float", 1.0, "Lunghezza della plastic hinge"),
                   ("Fy", "float", 3.0e8, "Tensione di snervamento"),
                   ("Phi_y", "float", 0.001, "Rotazione di snervamento"),
                   ("LambSlitF", "float", 1.0, "Fattore di slit"),
                   ("LambSlipD", "float", 1.0, "Fattore di slip")],
    },
    # --- Smorzamento / viscosi ---
    "Viscous": {
        "cmd": "Viscous", "family": "damper", "ndm": None,
        "params": [("C", "float", 1.0e5, "Coefficiente di smorzamento"),
                   ("alpha", "float", 0.5, "Esponente di velocità")],
    },
    "Viscoelastic": {
        "cmd": "Viscoelastic", "family": "damper", "ndm": None,
        "params": [("K", "float", 1.0e8, "Rigidità elastica"),
                   ("Cd", "float", 1.0e4, "Coefficiente di smorzamento"),
                   ("alpha", "float", 0.5, "Esponente di velocità (0-1)")],
    },
    "BoucWen": {
        "cmd": "BoucWen", "family": "hysteretic", "ndm": None,
        "params": [("alpha", "float", 0.01, "Rapporto post-snervamento"),
                   ("ko", "float", 1.0e8, "Rigidità elastica"),
                   ("n", "float", 1.0, "Esponente di snervamento"),
                   ("gamma", "float", 0.5, "Parametro gamma"),
                   ("beta", "float", 0.5, "Parametro beta"),
                   ("Ao", "float", 1.0, "Parametro Ao"),
                   ("deltaA", "float", 0.0, "Degrado di rigidità"),
                   ("deltaNu", "float", 0.0, "Degrado di duttilità"),
                   ("deltaEta", "float", 0.0, "Degrado di eta")],
    },
    # --- Soil p-y, t-z, q-z ---
    "PySimple1": {
        "cmd": "PySimple1", "family": "soil", "ndm": 2,
        "params": [("soilType", "int", 1, "Tipo di suolo (1=argilla morbida, 2=argilla rigida, 3=sabbia)"),
                   ("pult", "float", 1.0e5, "Capacità ultima [N/m]"),
                   ("y50", "float", 0.01, "Spostamento a metà capacità [m]"),
                   ("Cd", "float", 1.0e4, "Smorzamento radiativo"),
                   ("c", "float", 0.1, "Coefficiente di smorzamento viscoso")],
    },
    "TzSimple1": {
        "cmd": "TzSimple1", "family": "soil", "ndm": 2,
        "params": [("soilType", "int", 1, "Tipo di suolo"),
                   ("tult", "float", 1.0e5, "Capacità ultima di frizione"),
                   ("z50", "float", 0.01, "Spostamento a metà capacità"),
                   ("c", "float", 0.1, "Coefficiente di smorzamento")],
    },
    "QzSimple1": {
        "cmd": "QzSimple1", "family": "soil", "ndm": 2,
        "params": [("soilType", "int", 1, "Tipo di suolo"),
                   ("qult", "float", 1.0e6, "Capacità ultima di punta"),
                   ("z50", "float", 0.01, "Spostamento a metà capacità"),
                   ("c", "float", 0.1, "Coefficiente di smorzamento")],
    },
    # --- Inizializzazione / wrapper ---
    "InitStrainMaterial": {
        "cmd": "InitStrainMaterial", "family": "wrapper", "ndm": None,
        "params": [("-material", "int", 1, "Tag materiale da wrappare"),
                   ("-strain", "float", 0.0, "Deformazione iniziale")],
    },
    "InitStressMaterial": {
        "cmd": "InitStressMaterial", "family": "wrapper", "ndm": None,
        "params": [("-material", "int", 1, "Tag materiale da wrappare"),
                   ("-stress", "float", 0.0, "Tensione iniziale")],
    },
    "MinMaxMaterial": {
        "cmd": "MinMaxMaterial", "family": "wrapper", "ndm": None,
        "params": [("-material", "int", 1, "Tag materiale"),
                   ("-min", "float", -1e9, "Tensione minima"),
                   ("-max", "float", 1e9, "Tensione massima")],
    },
    "Fatigue": {
        "cmd": "Fatigue", "family": "wrapper", "ndm": None,
        "params": [("-material", "int", 1, "Tag materiale"),
                   ("-E0", "float", 0.191, "Parametro E0"),
                   ("-m", "float", -0.458, "Esponente m"),
                   ("-eps_min", "float", -0.08, "Deformazione minima per fatica")],
    },
    "PathIndependent": {
        "cmd": "PathIndependent", "family": "wrapper", "ndm": None,
        "params": [("-material", "int", 1, "Tag materiale path-independent")],
    },
}


# =============================================================================
# 2. nDMATERIALS (nDMaterial) - catalogo completo
# =============================================================================

ND_MATERIALS: Dict[str, dict] = {
    "ElasticIsotropic": {
        "cmd": "ElasticIsotropic", "family": "elastic", "ndm": None,
        "params": [("E", "float", 2.0e11, "Modulo elastico [Pa]"),
                   ("nu", "float", 0.3, "Coefficiente di Poisson"),
                   ("rho", "float", 0.0, "Massa volumica [kg/m^3] (opzionale)")],
        "extra": {"rho_optional": True},
    },
    "ElasticOrthotropic": {
        "cmd": "ElasticOrthotropic", "family": "elastic", "ndm": 3,
        "params": [("Ex", "float", 2.0e11, "Modulo X"),
                   ("Ey", "float", 2.0e11, "Modulo Y"),
                   ("Ez", "float", 2.0e11, "Modulo Z"),
                   ("nu_xy", "float", 0.3, "Poisson XY"),
                   ("nu_yz", "float", 0.3, "Poisson YZ"),
                   ("nu_xz", "float", 0.3, "Poisson XZ"),
                   ("Gxy", "float", 7.7e10, "Taglio XY"),
                   ("Gyz", "float", 7.7e10, "Taglio YZ"),
                   ("Gxz", "float", 7.7e10, "Taglio XZ"),
                   ("rho", "float", 0.0, "Massa volumica (opzionale)")],
    },
    "J2Plasticity": {
        "cmd": "J2Plasticity", "family": "plasticity", "ndm": None,
        "params": [("K", "float", 1.7e11, "Modulo di bulk"),
                   ("G", "float", 7.7e10, "Modulo di taglio"),
                   ("sigmaY", "float", 3.0e8, "Tensione di snervamento"),
                   ("Hi", "float", 0.0, "Modulo isotropo"),
                   ("Hk", "float", 0.0, "Modulo cinematico")],
    },
    "PlaneStress": {
        "cmd": "PlaneStress", "family": "wrapper", "ndm": 2,
        "params": [("-nd", "int", 1, "Tag materiale 3D da wrappare per piano di sforzo")],
    },
    "PlaneStrain": {
        "cmd": "PlaneStrain", "family": "wrapper", "ndm": 2,
        "params": [("-nd", "int", 1, "Tag materiale 3D da wrappare per piano di deformazione")],
    },
    "PlateFiber": {
        "cmd": "PlateFiber", "family": "wrapper", "ndm": None,
        "params": [("-nd", "int", 1, "Tag materiale 3D da wrappare per plate-fiber")],
    },
    "BeamFiber": {
        "cmd": "BeamFiber", "family": "wrapper", "ndm": None,
        "params": [("-nd", "int", 1, "Tag materiale 3D da wrappare per beam-fiber")],
    },
    "PlateRebar": {
        "cmd": "PlateRebar", "family": "wrapper", "ndm": None,
        "params": [("-nd", "int", 1, "Tag materiale"),
                   ("-rho", "float", 0.01, "Rapporto volumetrico"),
                   ("-angle", "float", 0.0, "Angolo direzione [deg]")],
    },
    "PressureIndependMultiYield": {
        "cmd": "PressureIndependMultiYield", "family": "soil", "ndm": None,
        "params": [("nd", "int", 2, "Numero di dimensioni (2 o 3)"),
                   ("rho", "float", 1.7, "Massa volumica [t/m^3]"),
                   ("refShearModul", "float", 1.0e5, "Modulo di taglio di riferimento"),
                   ("refBulkModul", "float", 3.0e5, "Modulo di bulk di riferimento"),
                   ("cohesi", "float", 5.0, "Coesione"),
                   ("peakShearStra", "float", 0.1, "Deformazione di taglio di picco"),
                   ("frictionAngle", "float", 0.0, "Angolo di attrito [deg]"),
                   ("refPress", "float", 100.0, "Pressione di riferimento"),
                   ("pressDependCoe", "float", 0.0, "Coefficiente dipendenza pressione"),
                   ("numberOfYieldSurf", "int", 20, "Numero superfici di snervamento"),
                   ("gredu", "float", 0.0, "Riduzione di G (opzionale)")],
    },
    "PressureDependMultiYield": {
        "cmd": "PressureDependMultiYield", "family": "soil", "ndm": None,
        "params": [("nd", "int", 2, "Numero di dimensioni (2 o 3)"),
                   ("rho", "float", 1.7, "Massa volumica [t/m^3]"),
                   ("refShearModul", "float", 1.0e5, "Modulo di taglio di riferimento"),
                   ("refBulkModul", "float", 3.0e5, "Modulo di bulk di riferimento"),
                   ("frictionAng", "float", 30.0, "Angolo di attrito [deg]"),
                   ("peakShearStra", "float", 0.1, "Deformazione di taglio di picco"),
                   ("refPress", "float", 100.0, "Pressione di riferimento"),
                   ("pressDependCoe", "float", 0.1, "Coefficiente dipendenza pressione"),
                   ("PTAng", "float", 26.0, "Angolo di transizione di fase [deg]"),
                   ("contrac", "float", 0.03, "Coefficiente di contrazione"),
                   ("dilat", "float", 0.0, "Coefficiente di dilatazione"),
                   ("numberOfYieldSurf", "int", 20, "Numero superfici di snervamento"),
                   ("gredu", "float", 0.0, "Riduzione di G"),
                   ("mResidual", "float", 0.0, "Rapporto di resistenza residua"),
                   ("contract_r1", "float", 1.0, "Coefficiente contrazione fase 1"),
                   ("contract_r2", "float", 0.0, "Coefficiente contrazione fase 2"),
                   ("dilate_r1", "float", 0.0, "Coefficiente dilatazione fase 1"),
                   ("dilate_r2", "float", 0.0, "Coefficiente dilatazione fase 2")],
    },
    "FluidSolidPorous": {
        "cmd": "FluidSolidPorous", "family": "soil", "ndm": None,
        "params": [("nd", "int", 2, "Numero di dimensioni"),
                   ("soilMatTag", "int", 1, "Tag materiale solido (PDMY/PIMY)"),
                   ("combinedBulkModul", "float", 1.0e5, "Modulo bulk combinato"),
                   ("pa", "float", 101.0, "Pressione atmosferica (opzionale)")],
    },
    "DruckerPrager": {
        "cmd": "DruckerPrager", "family": "plasticity", "ndm": None,
        "params": [("k", "float", 1.0e5, "Coesione"),
                   ("G", "float", 7.7e10, "Modulo di taglio"),
                   ("sigmaY", "float", 3.0e8, "Tensione di snervamento"),
                   ("K", "float", 1.7e11, "Modulo di bulk"),
                   ("rho", "float", 0.0, "Massa volumica"),
                   ("ht", "float", 0.0, "Modulo di indurimento"),
                   ("hm", "float", 0.0, "Modulo di softening")],
    },
    "CapPlasticity": {
        "cmd": "CapPlasticity", "family": "plasticity", "ndm": None,
        "params": [("E", "float", 2.0e11, "Modulo elastico"),
                   ("nu", "float", 0.3, "Poisson"),
                   ("rho", "float", 0.0, "Massa volumica"),
                   ("sigmaY", "float", 3.0e8, "Tensione di snervamento"),
                   ("Hi", "float", 0.0, "Modulo isotropo"),
                   ("Hk", "float", 0.0, "Modulo cinematico"),
                   ("K", "float", 0.0, "Parametro K")],
    },
    "AcousticMedium": {
        "cmd": "AcousticMedium", "family": "fluid", "ndm": None,
        "params": [("Kf", "float", 2.2e9, "Modulo di bulk del fluido"),
                   ("rho", "float", 1000.0, "Massa volumica")],
    },
    "ContactMaterial2D": {
        "cmd": "ContactMaterial2D", "family": "contact", "ndm": 2,
        "params": [("mu", "float", 0.3, "Coefficiente di attrito"),
                   ("G", "float", 7.7e10, "Modulo di taglio"),
                   ("K", "float", 1.7e11, "Modulo di bulk"),
                   ("t", "float", 0.01, "Soglia di contatto")],
    },
    "ContactMaterial3D": {
        "cmd": "ContactMaterial3D", "family": "contact", "ndm": 3,
        "params": [("mu", "float", 0.3, "Coefficiente di attrito"),
                   ("G", "float", 7.7e10, "Modulo di taglio"),
                   ("K", "float", 1.7e11, "Modulo di bulk"),
                   ("t", "float", 0.01, "Soglia di contatto")],
    },
    "PlasticDamageConcrete": {
        "cmd": "PlasticDamageConcrete", "family": "damage", "ndm": None,
        "params": [("E", "float", 3.0e10, "Modulo elastico"),
                   ("nu", "float", 0.2, "Poisson"),
                   ("ft", "float", 3.0e6, "Tensione di trazione"),
                   ("fc", "float", -3.0e7, "Tensione di compressione (negativa)"),
                   ("beta", "float", 0.6, "Parametro beta"),
                   ("Ap", "float", 1.0, "Parametro Ap"),
                   ("An", "float", 1.0, "Parametro An"),
                   ("Bn", "float", 0.5, "Parametro Bn")],
    },
}


# =============================================================================
# 3. ELEMENTI - catalogo completo per tipo Gmsh / OpenSees
# =============================================================================

# Mapping tipo Gmsh -> (nome OpenSees, n_nodi_richiesti, n_dim, n_dof_per_nodo, template_args)
# Per i casi in cui l'elemento è strettamente derivato dalla mesh Gmsh
GMSH_TO_OPENSEES: Dict[int, List[dict]] = {
    1: [  # Linea 2-nodi
        {"name": "truss", "n_nodes": 2, "dim": 1, "ndf": 3,
         "args": "A matTag",
         "desc": "Truss 2D/3D - solo assiale"},
        {"name": "corotTruss", "n_nodes": 2, "dim": 1, "ndf": 3,
         "args": "A matTag",
         "desc": "Truss corotazionale (grandi spostamenti)"},
        {"name": "elasticBeamColumn", "n_nodes": 2, "dim": 2, "ndf": 3,
         "args": "A E Iz transfTag",
         "desc": "Trave elastica 2D (richiede geomTransf)"},
        {"name": "elasticBeamColumn", "n_nodes": 2, "dim": 3, "ndf": 6,
         "args": "A E G J Iz Iy transfTag",
         "desc": "Trave elastica 3D (richiede geomTransf)"},
        {"name": "zeroLength", "n_nodes": 2, "dim": 0, "ndf": 3,
         "args": "-mat matTag1 matTag2 ... -dir dir1 dir2 ...",
         "desc": "Elemento zero-length con materiali per direzione"},
    ],
    2: [  # Triangolo 3-nodi
        {"name": "tri31", "n_nodes": 3, "dim": 2, "ndf": 2,
         "args": "thickness type matTag pressure rho",
         "desc": "Triangolo a 3 nodi piano (plane stress/strain)"},
    ],
    3: [  # Quadrilatero 4-nodi
        {"name": "quad", "n_nodes": 4, "dim": 2, "ndf": 2,
         "args": "thickness type matTag pressure rho",
         "desc": "Quadrilatero a 4 nodi (plane stress/strain)"},
        {"name": "bbarQuad", "n_nodes": 4, "dim": 2, "ndf": 2,
         "args": "thickness type matTag",
         "desc": "Quadrilatero B-Bar (costante pressione)"},
        {"name": "enhancedQuad", "n_nodes": 4, "dim": 2, "ndf": 2,
         "args": "thickness type matTag",
         "desc": "Quadrilatero enhanced strain"},
        {"name": "SSPquad", "n_nodes": 4, "dim": 2, "ndf": 2,
         "args": "type matTag h thickness",
         "desc": "SSPquad - stabilized single-point"},
    ],
    4: [  # Tetraedro 4-nodi
        {"name": "FourNodeTetrahedron", "n_nodes": 4, "dim": 3, "ndf": 3,
         "args": "matTag",
         "desc": "Tetraedro a 4 nodi lineare"},
    ],
    5: [  # Hex 8-nodi
        {"name": "stdBrick", "n_nodes": 8, "dim": 3, "ndf": 3,
         "args": "matTag",
         "desc": "Brick 8-nodi standard"},
        {"name": "bbarBrick", "n_nodes": 8, "dim": 3, "ndf": 3,
         "args": "matTag",
         "desc": "Brick B-Bar (costante pressione)"},
        {"name": "SSPbrick", "n_nodes": 8, "dim": 3, "ndf": 3,
         "args": "matTag h",
         "desc": "SSPbrick - stabilized single-point"},
    ],
    11: [  # Tetraedro 10-nodi
        {"name": "TenNodeTetrahedron", "n_nodes": 10, "dim": 3, "ndf": 3,
         "args": "matTag",
         "desc": "Tetraedro quadratico a 10 nodi"},
    ],
    # Tipi quad-shell per elementi di shell (aggiunti come pseudo-tipo 31=ShellMITC4)
    31: [  # placeholder per ShellMITC4 (quad 4-nodi shell)
        {"name": "ShellMITC4", "n_nodes": 4, "dim": 2, "ndf": 6,
         "args": "secTag",
         "desc": "Shell MIT-C4 a 4 nodi con sezione"},
        {"name": "ShellDKGQ", "n_nodes": 4, "dim": 2, "ndf": 6,
         "args": "secTag",
         "desc": "Shell DK-GQ (Discrete Kirchhoff)"},
    ],
}

# Catalogo esteso degli elementi OpenSees non derivati direttamente da Gmsh
# (per assegnazione manuale a entità)
ELEMENT_CATALOG: Dict[str, dict] = {
    # --- Truss ---
    "truss": {"family": "truss", "n_nodes": 2, "args": "A matTag",
              "notes": "Truss lineare 2D/3D"},
    "corotTruss": {"family": "truss", "n_nodes": 2, "args": "A matTag",
                   "notes": "Truss corotazionale (grandi spostamenti)"},
    "TrussSection": {"family": "truss", "n_nodes": 2, "args": "secTag",
                     "notes": "Truss con sezione (richiede section)"},
    # --- Beam / frame ---
    "elasticBeamColumn": {"family": "beam", "n_nodes": 2,
                          "args": "A E Iz|E G J Iz Iy transfTag",
                          "notes": "Trave elastica - richiede geomTransf"},
    "elasticTimoshenkoBeam": {"family": "beam", "n_nodes": 2,
                              "args": "E G A Iz Iy Avy Avz transfTag massDens",
                              "notes": "Trave elastica Timoshenko (shear deformation)"},
    "forceBeamColumn": {"family": "beam", "n_nodes": 2,
                        "args": "transfTag integrationTag massTag",
                        "notes": "Beam-column forza-based (richiede geomTransf e beamIntegration)"},
    "dispBeamColumn": {"family": "beam", "n_nodes": 2,
                       "args": "ndf transfTag integrationTag secTag massTag",
                       "notes": "Beam-column spostamento-based (richiede geomTransf e beamIntegration)"},
    "beamWithHinges": {"family": "beam", "n_nodes": 2,
                       "args": "E A Iz Iy G J transfTag npI lpI npJ lpJ secTagI secTagJ massDens",
                       "notes": "Beam con cerniere plastiche"},
    "nonlinearBeamColumn": {"family": "beam", "n_nodes": 2,
                            "args": "numIntgrPts secTag transfTag massDens iter maxIter",
                            "notes": "Alias per forceBeamColumn (legacy)"},
    # --- Plane ---
    "quad": {"family": "plane", "n_nodes": 4, "args": "thickness type matTag",
             "notes": "Quad 4-nodi (PlaneStress/PlaneStrain)"},
    "tri31": {"family": "plane", "n_nodes": 3, "args": "thickness type matTag",
              "notes": "Triangolo 3-nodi piano"},
    "bbarQuad": {"family": "plane", "n_nodes": 4, "args": "thickness type matTag",
                 "notes": "B-Bar quad"},
    "enhancedQuad": {"family": "plane", "n_nodes": 4, "args": "thickness type matTag",
                     "notes": "Enhanced strain quad"},
    "SSPquad": {"family": "plane", "n_nodes": 4, "args": "type matTag h thickness",
                "notes": "SSPquad stabilized"},
    # --- Shell ---
    "ShellMITC4": {"family": "shell", "n_nodes": 4, "args": "secTag",
                   "notes": "Shell MIT-C4 (richiede section)"},
    "ShellDKGQ": {"family": "shell", "n_nodes": 4, "args": "secTag",
                  "notes": "Shell DK-GQ"},
    "ShellNLDKGQ": {"family": "shell", "n_nodes": 4, "args": "secTag",
                    "notes": "Shell DK-GQ nonlinear"},
    "ASDShellQ4": {"family": "shell", "n_nodes": 4, "args": "secTag",
                   "notes": "ASD Shell Q4"},
    # --- Solid 3D ---
    "stdBrick": {"family": "solid", "n_nodes": 8, "args": "matTag",
                 "notes": "Brick 8-nodi standard"},
    "bbarBrick": {"family": "solid", "n_nodes": 8, "args": "matTag",
                  "notes": "Brick B-Bar"},
    "SSPbrick": {"family": "solid", "n_nodes": 8, "args": "matTag h",
                 "notes": "SSPbrick stabilized"},
    "FourNodeTetrahedron": {"family": "solid", "n_nodes": 4, "args": "matTag",
                            "notes": "Tetraedro 4-nodi"},
    "TenNodeTetrahedron": {"family": "solid", "n_nodes": 10, "args": "matTag",
                           "notes": "Tetraedro quadratico 10-nodi"},
    "20NodeBrick": {"family": "solid", "n_nodes": 20, "args": "matTag",
                    "notes": "Brick quadratico 20-nodi"},
    # --- Zero-length / contatto ---
    "zeroLength": {"family": "zero", "n_nodes": 2, "dim": 0,
                   "args": "-mat matTags -dir dirs",
                   "notes": "Elemento zero-length con materiali per direzione"},
    "zeroLengthSection": {"family": "zero", "n_nodes": 2,
                          "args": "secTag",
                          "notes": "Zero-length con sezione"},
    "zeroLengthContact2D": {"family": "contact", "n_nodes": 2, "dim": 2,
                            "args": "kn kt mu",
                            "notes": "Contatto zero-length 2D"},
    "zeroLengthContact3D": {"family": "contact", "n_nodes": 2, "dim": 3,
                            "args": "kn kt mu",
                            "notes": "Contatto zero-length 3D"},
    "zeroLengthInterface2D": {"family": "interface", "n_nodes": 2, "dim": 2,
                              "args": "-mat matTag -sNode sNode -pNode pNode",
                              "notes": "Interfaccia zero-length 2D"},
    "TwoNodeLink": {"family": "link", "n_nodes": 2,
                    "args": "matTags dirs",
                    "notes": "Two-node link con materiali per direzione"},
    # --- Bearing / isolatore ---
    "FlatSliderBearing": {"family": "bearing", "n_nodes": 2,
                          "args": "kInit muModel frnModel",
                          "notes": "Bearing a scorrimento piano"},
    "ElastomericBearing": {"family": "bearing", "n_nodes": 2,
                           "args": "kInit fy alpha mu",
                           "notes": "Bearing elastomerico"},
    "FPBearingPTV": {"family": "bearing", "n_nodes": 2,
                     "args": "mu0 R H A velParam",
                     "notes": "Bearing a pendolo frizionale"},
    # --- Joint ---
    "Joint2D": {"family": "joint", "n_nodes": 4, "dim": 2,
                "args": "matTag1 matTag2 matTag3 matTag4",
                "notes": "Joint 2D a 4 nodi"},
    # --- PFEM ---
    "PML2D": {"family": "pfem", "n_nodes": 9, "args": "bx by tx ty nx ny",
              "notes": "Perfectly Matched Layer 2D"},
}


# =============================================================================
# 4. SECTION (section) - catalogo
# =============================================================================

SECTION_CATALOG: Dict[str, dict] = {
    "Elastic": {
        "cmd": "Elastic", "family": "elastic",
        "params": [("E", "float", 2.0e11, "Modulo elastico"),
                   ("A", "float", 1.0e-2, "Area"),
                   ("Iz", "float", 8.33e-6, "Momento di inerzia z (2D)"),
                   ("Iy", "float", 8.33e-6, "Momento di inerzia y (3D)"),
                   ("G", "float", 7.7e10, "Modulo di taglio (3D, opzionale)"),
                   ("J", "float", 1.0e-5, "Momento di inerzia torsionale (3D)")],
        "extra": {"ndm_dep": True, "2d_args": "E A Iz", "3d_args": "E A Iz Iy G J"},
    },
    "Fiber": {
        "cmd": "Fiber", "family": "fiber",
        "params": [("-GJ", "float", 1.0e5, "Rigidità torsionale (opzionale, 2D)")],
        "extra": {"contains_fibers": True, "ndm_dep": True},
    },
    "Aggregator": {
        "cmd": "Aggregator", "family": "aggregator",
        "params": [("-sec", "int", 1, "Tag sezione da wrappare"),
                   ("-mat", "str", "1 2", "Tags materiali"),
                   ("-dir", "str", "1 2", "Direzioni")],
    },
    "Uniaxial": {
        "cmd": "Uniaxial", "family": "wrapper",
        "params": [("-mat", "str", "1 2", "Tags materiali"),
                   ("-dir", "str", "1 2", "Direzioni")],
    },
    "ElasticMembranePlateSection": {
        "cmd": "ElasticMembranePlateSection", "family": "shell",
        "params": [("E", "float", 2.0e11, "Modulo elastico"),
                   ("nu", "float", 0.3, "Poisson"),
                   ("h", "float", 0.1, "Spessore"),
                   ("rho", "float", 0.0, "Massa per unità di area")],
    },
    "PlateFiber": {
        "cmd": "PlateFiber", "family": "shell",
        "params": [("matTag", "int", 1, "Tag materiale plate-fiber"),
                   ("h", "float", 0.1, "Spessore")],
    },
    "LayeredShell": {
        "cmd": "LayeredShell", "family": "shell",
        "params": [("nLayers", "int", 3, "Numero strati"),
                   ("matTags", "str", "1 1 1", "Tags materiali per ogni strato"),
                   ("thicknesses", "str", "0.04 0.02 0.04", "Spessori per ogni strato")],
    },
    "Bidirectional": {
        "cmd": "Bidirectional", "family": "isolator",
        "params": [("mu", "float", 0.1, "Coefficiente di attrito"),
                   ("k1", "float", 1.0e8, "Rigidità elastica"),
                   ("fy", "float", 3.0e5, "Forza di snervamento"),
                   ("alpha", "float", 0.1, "Rapporto post-snervamento")],
    },
}


# =============================================================================
# 5. GEOMETRIC TRANSFORMATION (geomTransf)
# =============================================================================

GEOM_TRANSF: Dict[str, dict] = {
    "Linear": {
        "ndm": (2, 3),
        "args_2d": "vecxzX vecxzY vecxzZ",
        "args_3d": "vecxzX vecxzY vecxzZ -jntOffset dI1 dI2 dI3 dJ1 dJ2 dJ3",
        "notes": "Trasformazione lineare (piccoli spostamenti)",
    },
    "PDelta": {
        "ndm": (2, 3),
        "args_2d": "vecxzX vecxzY vecxzZ",
        "args_3d": "vecxzX vecxzY vecxzZ -jntOffset dI1 dI2 dI3 dJ1 dJ2 dJ3",
        "notes": "Include effetti P-Delta (geometrico)",
    },
    "Corotational": {
        "ndm": (2, 3),
        "args_2d": "vecxzX vecxzY vecxzZ",
        "args_3d": "vecxzX vecxzY vecxzZ -jntOffset dI1 dI2 dI3 dJ1 dJ2 dJ3",
        "notes": "Formulazione corotazionale (grandi spostamenti)",
    },
}


# =============================================================================
# 6. BEAM INTEGRATION
# =============================================================================

BEAM_INTEGRATION: Dict[str, dict] = {
    "Lobatto": {"n_points_arg": "np secTag", "notes": "Integrazione Gauss-Lobatto"},
    "Legendre": {"n_points_arg": "np secTag", "notes": "Integrazione Gauss-Legendre"},
    "Radau": {"n_points_arg": "np secTag", "notes": "Integrazione Gauss-Radau"},
    "NewtonCotes": {"n_points_arg": "np secTag", "notes": "Integrazione Newton-Cotes"},
    "Trapezoidal": {"n_points_arg": "np secTag", "notes": "Integrazione trapezoidale"},
    "UserDefined": {"n_points_arg": "np N*secTag N*weight", "notes": "Pesi definiti dall'utente"},
    "FixedLocation": {"n_points_arg": "np N*location N*secTag", "notes": "Posizioni fisse"},
    "HingeRadau": {"n_points_arg": "lpI lpJ", "notes": "Cerniera plastica Radau"},
    "HingeMidpoint": {"n_points_arg": "lpI lpJ", "notes": "Cerniera plastica midpoint"},
}


# =============================================================================
# 7. TIME SERIES
# =============================================================================

TIME_SERIES_TYPES: Dict[str, dict] = {
    "Linear": {
        "args": "-factor tStart",
        "tcl_template": "timeSeries Linear {tag} -factor {factor:g} -tStart {t_start:g};",
    },
    "Constant": {
        "args": "-factor",
        "tcl_template": "timeSeries Constant {tag} -factor {factor:g};",
    },
    "Trig": {
        "args": "tStart tEnd period -shift -factor",
        "tcl_template": ("timeSeries Trig {tag} {t_start:g} {t_end:g} {period:g} "
                         "-shift {shift:g} -factor {factor:g};"),
    },
    "Rectangular": {
        "args": "tStart tEnd -factor",
        "tcl_template": "timeSeries Rectangular {tag} {t_start:g} {t_end:g} -factor {factor:g};",
    },
    "Pulse": {
        "args": "tStart tEnd period width -factor",
        "tcl_template": ("timeSeries Pulse {tag} {t_start:g} {t_end:g} {period:g} "
                         "{width:g} -factor {factor:g};"),
    },
    "Triangle": {
        "args": "tStart tEnd period -factor -shift",
        "tcl_template": ("timeSeries Triangle {tag} {t_start:g} {t_end:g} {period:g} "
                         "-factor {factor:g} -shift {shift:g};"),
    },
    "Path": {
        "args": "-filePath|-dt+file|-time+values -factor",
        "tcl_template": "timeSeries Path {tag} {path_args} -factor {factor:g};",
    },
}


# =============================================================================
# 8. PATTERN
# =============================================================================

PATTERN_TYPES: Dict[str, dict] = {
    "Plain": {
        "args": "tag timeSeriesTag {body}",
        "tcl_template": "pattern Plain {tag} {ts_tag} {{\n{body}\n}}",
        "body_required": True,
    },
    "UniformExcitation": {
        "args": "dir -accel seriesTag <-vel seriesTag> <-disp seriesTag> <-fact>",
        "tcl_template": "pattern UniformExcitation {tag} {dir} -accel {accel_ts};",
    },
    "MultipleSupport": {
        "args": "tag {body}",
        "tcl_template": "pattern MultipleSupport {tag} {{\n{body}\n}}",
        "body_required": True,
    },
}


# =============================================================================
# 9. CONSTRAINT HANDLER, NUMBERER, SYSTEM, ALGORITHM, INTEGRATOR, TEST, ANALYSIS
# =============================================================================

CONSTRAINT_HANDLERS: Dict[str, dict] = {
    "Plain": {"args": [], "notes": "Constraint handler semplice"},
    "Penalty": {"args": ["alpha1", "alpha2"], "defaults": [1.0e12, 1.0e12],
                "notes": "Penalty (richiede alpha1, alpha2)"},
    "Lagrange": {"args": ["alpha1", "alpha2"], "defaults": [1.0, 1.0],
                 "notes": "Lagrange (alpha opzionali)"},
    "Transformation": {"args": [], "notes": "Transformation (MP constraint)"},
}

NUMBERERS: Dict[str, dict] = {
    "Plain": {"args": [], "notes": "Numeratore plain"},
    "RCM": {"args": [], "notes": "Reverse Cuthill-McKee"},
    "AMD": {"args": [], "notes": "Approximate Minimum Degree"},
}

SYSTEMS: Dict[str, dict] = {
    "BandGeneral": {"args": [], "notes": "Banda generale (Lapack)"},
    "BandSPD": {"args": [], "notes": "Banda simmetrica definita positiva"},
    "ProfileSPD": {"args": [], "notes": "Profilo SPD"},
    "SparseGeneral": {"args": [], "notes": "Sparse generale (SuperLU)"},
    "SparseSYM": {"args": [], "notes": "Sparse simmetrica"},
    "FullGeneral": {"args": [], "notes": "Piena generale"},
    "Umfpack": {"args": [], "notes": "UmfPack"},
    "Mumps": {"args": [], "notes": "MUMPS"},
}

ALGORITHMS: Dict[str, dict] = {
    "Linear": {"args": ["-secant", "-initial"], "defaults": [],
               "notes": "Algoritmo lineare (1 iterazione)"},
    "Newton": {"args": ["-secant", "-initial"], "defaults": [],
               "notes": "Newton-Raphson"},
    "ModifiedNewton": {"args": [], "notes": "Newton modificato"},
    "NewtonLineSearch": {"args": ["-type", "-tol", "-maxIter"],
                          "defaults": ["Bisection", 0.8, 10],
                          "notes": "Newton con line search"},
    "KrylovNewton": {"args": ["-iterate", "-increment", "-maxDim"],
                     "defaults": ["standard", "test", 3],
                     "notes": "Krylov sub-space Newton"},
    "BFGS": {"args": ["-secant", "-count"], "defaults": [False, 0],
              "notes": "Broyden-Fletcher-Goldfarb-Shanno"},
    "Broyden": {"args": ["-secant", "-count"], "defaults": [False, 0],
                 "notes": "Broyden"},
}

INTEGRATORS: Dict[str, dict] = {
    # --- Static ---
    "LoadControl": {"args": ["lambda", "numIncr", "minLambda", "maxLambda"],
                    "defaults": [0.1, 1, 0.1, 1.0],
                    "notes": "Static - controllo del carico",
                    "analysis": "Static"},
    "DisplacementControl": {"args": ["node", "dof", "incr", "numIncr", "minDisp", "maxDisp"],
                            "defaults": [0, 1, 0.1, 1, 0.1, 1.0],
                            "notes": "Static - controllo spostamento",
                            "analysis": "Static"},
    "ArcLength": {"args": ["arcLength", "alpha"], "defaults": [0.1, 0.0],
                  "notes": "Static - arco-length",
                  "analysis": "Static"},
    "MinUnbalDispNorm": {"args": ["dlambda1Jd", "Jd", "minLambda", "maxLambda"],
                         "defaults": [0.1, 1.0, 0.1, 1.0],
                         "notes": "Static - min unbalanced disp",
                         "analysis": "Static"},
    # --- Transient ---
    "Newmark": {"args": ["gamma", "beta"], "defaults": [0.5, 0.25],
                "notes": "Transient - Newmark",
                "analysis": "Transient"},
    "HHT": {"args": ["alpha"], "defaults": [-0.3],
            "notes": "Transient - Hilber-Hughes-Taylor",
            "analysis": "Transient"},
    "GeneralizedAlpha": {"args": ["alphaM", "alphaF", "beta", "gamma"],
                          "defaults": [0.5, 0.5, 0.25, 0.5],
                          "notes": "Transient - generalized-alpha",
                          "analysis": "Transient"},
    "CentralDifference": {"args": [], "notes": "Explicit - central difference",
                          "analysis": "Transient"},
    "ExplicitDifference": {"args": [], "notes": "Explicit difference",
                            "analysis": "Transient"},
    "TRBDF2": {"args": [], "notes": "Transient - TRBDF2 (Bathe)",
                "analysis": "Transient"},
    "BackwardEuler": {"args": [], "notes": "Implicit - backward Euler",
                      "analysis": "Transient"},
}

TESTS: Dict[str, dict] = {
    "NormUnbalance": {"args": ["tol", "iter", "pFlag", "nType"],
                       "defaults": [1e-6, 25, 0, 2],
                       "notes": "Norm of residual force"},
    "NormDispIncr": {"args": ["tol", "iter", "pFlag", "nType"],
                      "defaults": [1e-6, 25, 0, 2],
                      "notes": "Norm of displacement increment"},
    "EnergyIncr": {"args": ["tol", "iter", "pFlag"],
                   "defaults": [1e-6, 25, 0],
                   "notes": "Energy increment"},
    "RelativeNormUnbalance": {"args": ["tol", "iter", "pFlag"],
                              "defaults": [1e-6, 25, 0],
                              "notes": "Relative residual norm"},
    "RelativeNormDispIncr": {"args": ["tol", "iter", "pFlag"],
                              "defaults": [1e-6, 25, 0],
                              "notes": "Relative disp increment"},
    "RelativeEnergyIncr": {"args": ["tol", "iter", "pFlag"],
                            "defaults": [1e-6, 25, 0],
                            "notes": "Relative energy increment"},
    "FixedNumIter": {"args": ["numIter", "pFlag"], "defaults": [1, 0],
                     "notes": "Fixed number of iterations"},
    "NormDispAndUnbalance": {"args": ["tolDisp", "tolForce", "iter", "pFlag"],
                              "defaults": [1e-6, 1e-6, 25, 0],
                              "notes": "Combined disp + unbalance"},
}

ANALYSIS_TYPES: List[str] = ["Static", "Transient", "VariableTimeStepTransient", "PFEM"]


# =============================================================================
# 10. RECORDERS
# =============================================================================

RECORDER_TYPES: Dict[str, dict] = {
    "Node": {
        "tcl_template": "recorder Node -file {file} -node {nodes} -dof {dofs} {response}",
        "valid_responses": ["disp", "vel", "accel", "incrDisp", "reaction", "unbalance", "pressure", "eigen"],
    },
    "EnvelopeNode": {
        "tcl_template": "recorder EnvelopeNode -file {file} -node {nodes} -dof {dofs} {response}",
        "valid_responses": ["disp", "vel", "accel", "incrDisp", "reaction"],
    },
    "Element": {
        "tcl_template": "recorder Element -file {file} -ele {eles} {response}",
        "valid_responses": ["force", "deformation", "stress", "strain", "stresses",
                             "strains", "basicForce", "basicDeformation", "basicStiffness",
                             "sectionForce", "sectionDeformation", "chordRotation",
                             "plasticRotation", "energy"],
    },
    "EnvelopeElement": {
        "tcl_template": "recorder EnvelopeElement -file {file} -ele {eles} {response}",
        "valid_responses": ["force", "deformation", "stress", "strain"],
    },
    "Drift": {
        "tcl_template": "recorder Drift -file {file} -iNode {i} -jNode {j} -dof {dof} -perpDirn {perp}",
        "valid_responses": [],
    },
    "Pattern": {
        "tcl_template": "recorder Pattern -file {file} -time -load",
        "valid_responses": [],
    },
    "ElementRemoval": {
        "tcl_template": "recorder ElementRemoval -file {file} -ele {eles}",
        "valid_responses": [],
    },
}

RECORDER_OPTIONS: List[str] = ["-file", "-fileCSV", "-xml", "-binary", "-precision",
                                "-scientific", "-closeOnWrite", "-time", "-dT",
                                "-timeSeries", "-nodeRange", "-eleRange", "-region"]


# =============================================================================
# 11. PARAMETERS (parameter / updateParameter / setParameter)
# =============================================================================

PARAMETER_TARGETS: Dict[str, dict] = {
    "blank": {"tcl_template": "parameter {tag} {value}",
              "needs_value": True, "needs_object": False},
    "element": {"tcl_template": "parameter {tag} element {eleTag} {path}",
                "needs_value": False, "needs_object": True, "object_arg": "eleTag"},
    "node": {"tcl_template": "parameter {tag} node {nodeTag} disp {dof}",
             "needs_value": False, "needs_object": True, "object_arg": "nodeTag",
             "extra_args": ["dof"]},
    "pattern": {"tcl_template": "parameter {tag} pattern {patternTag} lambda",
                "needs_value": False, "needs_object": True, "object_arg": "patternTag"},
    "loadPattern": {"tcl_template": "parameter {tag} loadPattern {loadTag} {path}",
                    "needs_value": False, "needs_object": True, "object_arg": "loadTag",
                    "extra_args": ["path"]},
}

UPDATE_COMMANDS: Dict[str, dict] = {
    "none": {"tcl_template": "", "notes": "Nessun comando di update"},
    "updateMaterialStage": {"tcl_template": "updateMaterialStage -material {matTag} {stage} {value};",
                             "notes": "Update stato materiale (0=elastic, 1=plastic, 2=liquefied)"},
    "updateParameter": {"tcl_template": "updateParameter {tag} {value};",
                         "notes": "Update valore di un parameter pre-definito"},
    "updateMaterials": {"tcl_template": "updateMaterials -material {matTag} {paramName} {value};",
                        "notes": "Update di un parametro specifico di un materiale"},
    "setParameter": {"tcl_template": "setParameter -val {value} -eleRange {start} {end} {paramName};",
                      "notes": "Set di un parametro su un range di elementi"},
}


# =============================================================================
# 12. ELE LOAD TYPES
# =============================================================================

ELEMENT_LOAD_TYPES: Dict[str, dict] = {
    "-beamUniform": {"args": ["Wy", "Wx", "aL", "bL", "Wy2", "Wx2"],
                     "3d_args": ["Wy", "Wz", "Wx", "aL", "bL", "Wy2", "Wz2", "Wx2"],
                     "notes": "Carico distribuito uniforme su trave"},
    "-beamPoint": {"args": ["P", "xDivL", "N"], "3d_args": ["Py", "Pz", "xDivL", "N"],
                   "notes": "Carico puntiforme su trave"},
    "-SurfaceLoad": {"args": ["Fx", "Fy", "Fz"], "notes": "Carico su superficie"},
    "-SelfWeight": {"args": ["Fx", "Fy", "Fz"], "notes": "Peso proprio"},
    "-BrickSelfWeight": {"args": [], "notes": "Peso proprio brick"},
}


# =============================================================================
# Helpers
# =============================================================================

def list_material_families() -> List[str]:
    """Restituisce le famiglie di materiali disponibili."""
    fams = set()
    for m in UNIAXIAL_MATERIALS.values():
        fams.add(m["family"])
    for m in ND_MATERIALS.values():
        fams.add(m["family"])
    return sorted(fams)


def list_elements_by_family() -> Dict[str, List[str]]:
    """Restituisce un dict famiglia -> lista di nomi elemento."""
    res: Dict[str, List[str]] = {}
    for name, info in ELEMENT_CATALOG.items():
        res.setdefault(info["family"], []).append(name)
    return res


def get_material_schema(model: str) -> Optional[dict]:
    """Restituisce lo schema materiale (cerca in uniaxial e nD)."""
    return UNIAXIAL_MATERIALS.get(model) or ND_MATERIALS.get(model)


def is_uniaxial(model: str) -> bool:
    return model in UNIAXIAL_MATERIALS


def is_ndmaterial(model: str) -> bool:
    return model in ND_MATERIALS


def get_element_info(name: str) -> Optional[dict]:
    return ELEMENT_CATALOG.get(name)


def get_gmsh_to_opensees_options(gmsh_type: int) -> List[dict]:
    """Restituisce le opzioni elemento OpenSees per un tipo Gmsh."""
    return GMSH_TO_OPENSEES.get(gmsh_type, [])
