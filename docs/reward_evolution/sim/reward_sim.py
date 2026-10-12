#!/usr/bin/env python3
# Future Reward Evolution — fine simulation (ANALYSIS ONLY; no consensus).
# No winner chosen a priori. Compares models x intervals x scenarios.
import json, math, csv, io

BT=600; BLOCKS_DAY=86400//BT; BLOCKS_YEAR=BLOCKS_DAY*365   # 144/day, 52560/yr
# Subsidy epochs (Feigenbaum decay ~9.03%/yr; epoch=131,553 blocks). Illustrative values.
SUBSIDY={'current(epoch0)':7.851,'next(epoch1)':7.851*0.9097,'later(epoch2)':7.851*0.9097**2}
MODELS={'CURRENT 50/50/0':(0.50,0.50,0.00),'75/20/5':(0.75,0.20,0.05),
        '80/15/5':(0.80,0.15,0.05),'80/10/10':(0.80,0.10,0.10),'70/25/5':(0.70,0.25,0.05)}
INTERVALS=[1000,2500,4320,5000,10000]
# scenarios: list of hashrate shares (sum=1). Sybil handled specially.
SCEN={
 'S1 high-concentration':[0.56,0.20,0.10,0.06,0.04,0.04],
 'S2 moderate':[0.30,0.14,0.12,0.11,0.10,0.08,0.06,0.05,0.04],
 'S3 healthy-decentralized':[0.14,0.13,0.12,0.10,0.09,0.08,0.07,0.07,0.06,0.05,0.04,0.03,0.02],
 'S4 many-small':[0.05,0.05,0.05,0.04,0.04,0.04,0.04,0.04,0.04,0.04,0.03,0.03,0.03,0.03,0.03,0.03,0.03,0.03,0.03,0.03,0.03,0.03,0.03,0.03,0.03],
}

def gini(x):
    x=sorted(x); n=len(x); s=sum(x)
    if s==0: return 0.0
    cum=sum((i+1)*v for i,v in enumerate(x))
    return (2*cum)/(n*s)-(n+1)/n
def hhi(x):
    s=sum(x)
    return sum((v/s)**2 for v in x) if s>0 else 0.0

def eligible_mask(shares):
    # anti-dominance: exclude identities with >=10% of recent blocks (approx = hashrate share) from DTD/jackpot
    # gate armed only when >=11 distinct miners
    N=len(shares); gate=N>=11
    return [(not (gate and h>=0.10)) for h in shares]

def simulate(shares, model, I, S):
    m,d,j=model
    N=len(shares); elig=eligible_mask(shares); ne=sum(elig)
    pe=1.0/ne if ne>0 else 0.0
    # per-block pools
    # jackpot accumulates j*S per block over I blocks, paid once per interval to one eligible identity
    J=j*S*I                      # jackpot prize per draw (SOST)
    draws={p:BLOCKS_YEAR//I* (dd) for p,dd in []}  # placeholder
    per_year_draws=BLOCKS_YEAR/I
    rows=[]
    for i,h in enumerate(shares):
        is_e=elig[i]
        # expected annual income
        block_y = m*h*S*BLOCKS_YEAR
        dtd_y   = (d*pe*S*BLOCKS_YEAR) if is_e else 0.0     # every block, uniform among eligible
        p_win   = pe if is_e else 0.0
        jack_y  = per_year_draws * p_win * J                 # expected jackpot income/yr
        tot_y   = block_y+dtd_y+jack_y
        # variance (annual): block+dtd ~ low variance; jackpot = sum of per_year_draws Bernoulli(p_win)*J
        var_y   = per_year_draws * p_win*(1-p_win) * (J**2)
        cov     = (math.sqrt(var_y)/tot_y) if tot_y>0 else 0.0
        # P(no jackpot) over 30/90/365 days
        def pnone(days):
            dd=days*BLOCKS_DAY/I
            return (1-p_win)**dd if p_win>0 else 1.0
        rows.append({'miner':f'm{i}','hash':h,'eligible':is_e,'block_y':block_y,'dtd_y':dtd_y,
                     'jack_y':jack_y,'total_y':tot_y,'cov':cov,
                     'uplift_vs_hash': (tot_y/(h*S*BLOCKS_YEAR)) if h>0 else 0.0,
                     'p_no_jack_30d':pnone(30),'p_no_jack_90d':pnone(90),'p_no_jack_1y':pnone(365)})
    inc=[r['total_y'] for r in rows]
    return {'prize_SOST':J,'draws_per_year':per_year_draws,'gini':gini(inc),'hhi':hhi(inc),
            'rows':rows,'eligible_count':ne,'N':N}

def supply_check(model):
    return abs(sum(model)-1.0)<1e-9

# ---- run ----
out={'meta':{'block_time_s':BT,'blocks_day':BLOCKS_DAY,'blocks_year':BLOCKS_YEAR,
             'subsidy':SUBSIDY,'note':'ANALYSIS ONLY — no consensus, no activation height, illustrative SOST amounts'},
     'supply_conservation':{k:supply_check(v) for k,v in MODELS.items()},
     'results':[]}
S=SUBSIDY['current(epoch0)']
csv_rows=[['scenario','model','interval','prize_SOST','draws/yr','gini','hhi',
           'small_uplift','dominant_total%','dominant_vs_hash','small_cov','small_pNoJack_1y']]
for sname,shares in SCEN.items():
    for mname,model in MODELS.items():
        for I in INTERVALS:
            r=simulate(shares,model,I,S)
            dom=max(r['rows'],key=lambda x:x['hash'])
            small=min(r['rows'],key=lambda x:x['hash'])
            totY=sum(x['total_y'] for x in r['rows'])
            rec={'scenario':sname,'model':mname,'interval':I,'prize_SOST':round(r['prize_SOST'],1),
                 'draws_per_year':round(r['draws_per_year'],1),'gini':round(r['gini'],4),'hhi':round(r['hhi'],4),
                 'eligible_count':r['eligible_count'],
                 'small_uplift':round(small['uplift_vs_hash'],3),'small_cov':round(small['cov'],3),
                 'small_pNoJack_1y':round(small['p_no_jack_1y'],4),
                 'dominant_total_pct':round(100*dom['total_y']/totY,2),'dominant_hash_pct':round(100*dom['hash'],2),
                 'dominant_vs_hash':round(dom['uplift_vs_hash'],3)}
            out['results'].append(rec)
            csv_rows.append([sname,mname,I,rec['prize_SOST'],rec['draws_per_year'],rec['gini'],rec['hhi'],
                             rec['small_uplift'],rec['dominant_total_pct'],rec['dominant_vs_hash'],rec['small_cov'],rec['small_pNoJack_1y']])

# Sybil analysis (S5): one operator with 30% total hash splits into K identities vs keeping 1.
# Model: DTD/jackpot uniform among eligible identities. Eligibility needs a qualifying recent block.
# If splitting into K identities each gets hash/K; over recency window W=288 blocks a miner expects hash_share*288 blocks.
# An identity is 'recency-eligible' only if it is expected to mine >=1 block in W: hash_i*288 >= 1.
sybil={'setup':'one operator = 30% total hash; compare 1 identity vs split into K; others = 70% across 10 miners',
       'recency_window_blocks':288,'cases':[]}
others=[0.07]*10
for K in [1,2,5,10,30,100]:
    op=[0.30/K]*K
    shares=op+others
    # recency eligibility: expected blocks in 288 = share*288; eligible if >=1 (prob-based: 1-(1-share)^288 ~ ; use expected>=1 cut)
    def rec_elig(sh): return (sh*288)>=1.0
    elig=[rec_elig(s) for s in shares]
    # among recency-eligible, uniform DTD/jackpot
    ne=sum(elig); pe=1/ne if ne else 0
    # operator's share of DTD+jackpot pool = (#op identities eligible)/ne
    op_elig=sum(1 for s in op if rec_elig(s))
    op_pool=op_elig*pe
    # operator block share = 0.30 always (hash-proportional)
    # under 75/20/5: operator total expected share of emission:
    m,d,j=MODELS['75/20/5']
    op_total=m*0.30 + (d+j)*op_pool
    sybil['cases'].append({'K':K,'op_hash':0.30,'op_identities':K,'op_eligible_identities':op_elig,
                           'eligible_total':ne,'op_pool_share':round(op_pool,3),
                           'op_total_emission_share_75_20_5':round(op_total,3),
                           'verdict':'splitting below recency threshold -> identities drop out' if op_elig<K else 'all identities eligible'})
out['sybil']=sybil

open('docs/reward_evolution/sim/reward_sim_results.json','w').write(json.dumps(out,indent=1))
with open('docs/reward_evolution/sim/reward_sim_results.csv','w',newline='') as cf:
    csv.writer(cf).writerows(csv_rows)
print("WROTE results.json + results.csv | models:",len(MODELS),"scenarios:",len(SCEN),"intervals:",len(INTERVALS),"rows:",len(out['results']))
print("supply conservation:",out['supply_conservation'])
