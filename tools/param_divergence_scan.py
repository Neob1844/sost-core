#!/usr/bin/env python3
"""Encuentra los bloques cuya transcripción CX no verifica con la tabla de
perfiles actual.

Por qué existe. El escáner de cASERT (tools/casert_replay_scanner.cpp) compara
lo que el validador RECALCULA -- bits_q y profile_index -- contra lo que el
bloque declara. Hay una segunda clase de discrepancia que ese escáner no puede
ver, porque no recalcula nada: los cuatro parámetros de estabilidad
(scale, steps, k, margin) con los que se verifica la transcripción salen de la
tabla canónica del código, no del bloque. Si la tabla cambió después de que el
bloque se minara, la transcripción no verifica y el bloque se rechaza al
sincronizar desde génesis -- aunque bits_q y profile_index cuadren.

Eso es justo lo que pasó entre el bloque 4715 y el 5038 de abril de 2026.

Este script lee chain.json y lista todos los bloques cuyos stab_* guardados no
coinciden con los que la tabla vigente daría para su profile_index a su altura.
Su salida es la tabla HISTORIC_PARAM_EXCEPTIONS de src/sost-node.cpp.

Uso:  python3 tools/param_divergence_scan.py /ruta/a/chain.json [--cpp]

Aviso: las dos tablas de abajo son copias de include/sost/params.h. Si allí se
toca una fila, hay que tocarla aquí, y entonces este script dirá qué bloques
históricos dejan de verificar por culpa de ese cambio. Ese es precisamente su
valor: convierte un cambio de tabla en una lista concreta de bloques rotos
ANTES de publicarlo.
"""
import json, io, sys

# include/sost/params.h — struct CasertProfile { scale, steps, k, margin }
LEGACY_H_MIN = -4      # CASERT_H_MIN_LEGACY
NEW_H_MIN    = -7      # CASERT_H_MIN
V8_HEIGHT    = 5750    # CASERT_CEILING_H13_HEIGHT

_TAIL = [(2,8,7,115),(2,8,8,115),(2,9,8,115),(2,9,9,115),(2,10,9,115),(2,10,10,115),
         (2,11,10,115),(2,11,11,115),(2,12,11,115),(2,12,12,115),(2,13,12,115),(2,13,13,115),
         (2,14,13,115),(2,14,14,115),(2,15,14,115),(2,15,15,115),(2,16,15,115),(2,16,16,115),
         (2,17,16,115),(2,17,17,115),(2,18,17,115),(2,18,18,115),(2,19,18,115),(2,19,19,115),
         (2,20,19,115),(2,20,20,115)]

LEGACY = [(1,2,3,280),(1,3,3,240),(1,4,3,225),(1,4,4,205),(1,4,4,185),
          (1,5,4,170),(1,5,5,160),(1,6,5,150),(1,6,6,145),(2,5,5,140),
          (2,6,5,135),(2,6,6,130),(2,7,6,125),(2,7,7,120)] + _TAIL

NEW    = [(1,1,1,200),(1,2,1,195),(1,2,2,190),(1,3,2,185),(1,3,3,180),(1,4,3,175),
          (1,4,4,170),(1,4,4,165),(1,5,4,160),(1,5,5,155),(1,6,5,150),(1,6,6,145),
          (2,5,5,140),(2,6,5,135),(2,6,6,130),(2,7,6,125),(2,7,7,120)] + _TAIL


def expected(profile_index, height):
    """Lo mismo que casert_apply_profile(), incluido el recorte de índice."""
    if height >= V8_HEIGHT:
        table, lo = NEW, NEW_H_MIN
    else:
        table, lo = LEGACY, LEGACY_H_MIN
    i = profile_index - lo
    if i < 0:
        i = 0
    if i >= len(table):
        i = len(table) - 1
    return table[i]


def scan(path):
    out = []
    with io.open(path, encoding='utf-8') as f:
        for line in f:
            s = line.strip().rstrip(',')
            if not s.startswith('{"block_id"'):
                continue
            b = json.loads(s)
            if b.get('height', 0) == 0 or b.get('profile_index') is None:
                continue
            got = (b['stab_scale'], b['stab_steps'], b['stab_k'], b['stab_margin'])
            exp = expected(b['profile_index'], b['height'])
            if got != exp:
                out.append((b['height'], b['profile_index'], got, exp, b['block_id']))
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    rows = scan(sys.argv[1])
    if '--cpp' in sys.argv:
        for h, pi, got, _exp, bid in rows:
            print('    { %5d, "%s", %d, %2d, %2d, %3d },' % (h, bid, got[0], got[1], got[2], got[3]))
        return 0
    print('bloques con parámetros divergentes: %d' % len(rows))
    if not rows:
        return 0
    print('rango: %d .. %d' % (rows[0][0], rows[-1][0]))
    print('%-7s %-4s %-22s %-22s' % ('altura', 'perfil', 'guardado', 'tabla actual'))
    for h, pi, got, exp, _bid in rows:
        print('%-7d H%-5d %-22s %-22s' % (h, pi, str(got), str(exp)))
    return 1


if __name__ == '__main__':
    sys.exit(main())
