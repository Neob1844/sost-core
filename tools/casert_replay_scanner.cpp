// casert_replay_scanner — ¿puede el binario ACTUAL revalidar la historia?
//
// Recorre la cadena y, para cada altura, recomputa bits_q y el perfil base con
// las MISMAS dos llamadas que hace el validador en src/sost-node.cpp, con sus
// mismas puertas por altura:
//
//     bits_q : casert_next_bitsq(meta, h, h >= CASERT_V6PP_HEIGHT        ? ts : 0)
//     perfil : casert_compute   (meta, h, h >= CASERT_V6_CALIBRATION_HEIGHT ? ts : 0)
//
// Reproducir esas puertas NO es un detalle: un escaneo que pase now_time=0 en
// todas las alturas produce 153 falsos positivos repartidos por toda la cadena.
// Con las puertas correctas el resultado es 19 bloques, todos entre 4160 y 5410.
//
// USO
//   1) volcar los metadatos desde chain.json, una línea por bloque:
//        altura timestamp bits_q profile_index
//   2) ./casert_replay_scanner metas.txt <desde> <hasta>
//
//   Salida: una línea "BQ h cadena recalculado" o "PI h declarado base" por
//   divergencia, y un RESUMEN final.
//
// RESULTADO ESPERADO (cadena canónica, rango 3555..punta): exactamente
//   9 divergencias de bits_q  -> 5150..5158
//  10 divergencias de perfil  -> 4160, 5320, 5321, 5335, 5362, 5363,
//                                5386, 5394, 5401, 5410
// Cualquier otra cosa es una regresión: o el motor cambió, o la cadena cambió.
//
// Corroborado de forma independiente: dos nodos oficiales v16.2.3 sincronizando
// desde génesis se detuvieron en 4160 y en 5150, las dos primeras predicciones
// de este escáner, sin conocerlas.

#include "sost/pow/casert.h"
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
// Reproduce EXACTAMENTE las dos llamadas del validador de sost-node.cpp:
//   bits_q : casert_next_bitsq(meta, h, h >= CASERT_V6PP_HEIGHT        ? ts : 0)
//   perfil : casert_compute   (meta, h, h >= CASERT_V6_CALIBRATION_HEIGHT ? ts : 0)
int main(int argc,char**argv){
    std::vector<sost::BlockMeta> all; std::vector<uint32_t> dbq; std::vector<int32_t> dpi; std::vector<long long> dts;
    std::ifstream f(argv[1]); std::string line;
    while(std::getline(f,line)){ if(line.empty())continue; std::istringstream is(line);
        long long h,t; unsigned long long bq; long long pi; is>>h>>t>>bq>>pi;
        sost::BlockMeta m{}; m.height=h; m.time=t; m.powDiffQ=(uint32_t)bq; m.profile_index=(int32_t)pi;
        all.push_back(m); dbq.push_back((uint32_t)bq); dpi.push_back((int32_t)pi); dts.push_back(t); }
    long long from=atoll(argv[2]), to=atoll(argv[3]);
    long long nbq=0,npi=0;
    std::vector<sost::BlockMeta> win;
    for(long long h=0; h<=to && h<(long long)all.size(); ++h){
        if(h>=from){
            long long t_bq = (h >= sost::CASERT_V6PP_HEIGHT) ? dts[h] : 0;
            long long t_pi = (h >= sost::CASERT_V6_CALIBRATION_HEIGHT) ? dts[h] : 0;
            uint32_t exp_bq = sost::casert_next_bitsq(win, h, t_bq);
            auto dec = sost::casert_compute(win, h, t_pi);
            if(exp_bq != dbq[h]){ printf("BQ %lld %u %u\n",h,dbq[h],exp_bq); nbq++; }
            if(dpi[h] > dec.profile_index){ printf("PI %lld %d %d\n",h,dpi[h],dec.profile_index); npi++; }
        }
        win.push_back(all[h]);
    }
    printf("RESUMEN rango %lld..%lld  bits_q divergentes=%lld  perfil por encima de la base=%lld\n",from,to,nbq,npi);
    return 0;
}
