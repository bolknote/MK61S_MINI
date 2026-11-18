"""Decode the disjoint foreground ledger and the physical CS overlap at frame 2440."""
import argparse
import csv
from pathlib import Path
import re

VISIBLE = [(78,0,86,64),(224,0,82,72),(32,64,116,16),
            (272,72,42,48),(0,80,112,40),(0,120,80,80),(288,120,32,80)]
BASE = ["frame entry and VM","presentation","frame fingerprint","timer","LCD fence","next VM",
        "PCM mixer","VM polygons","VM copy","VM fill"]
FIRST = len(BASE)


def need(test,detail):
    if not test:
        raise ValueError(detail)


def records(log,tag):
    prefix=tag+" "
    return [[int(n) for n in line[len(prefix):].split()] for line in log.splitlines() if line.startswith(prefix)]


def measure(us,ticks):
    # SM1 decrements X once per two clk_sys cycles while GPIO13 is low.
    return dict(wall_us=us,cs_low_ticks=ticks,cs_low_us=round(ticks*2/125,3),
                cs_high_us=round(us-ticks*2/125,3))


def parse(log, mode=None, host=False):
    need("SCK FIRST 2350 4FC268F0" in log and "SCK END 0 0" in log and "SCK FAIL" not in log,"scene or PCM")
    if host:
        need([int(n) for n in re.findall(r"^SCK H (\d+) [0-9A-F]{8}$",log,re.M)]==list(range(2387,2454)),
             "67 frames did not pass VM readback")
    else:
        need("APP_FLOW_RESULT=0" in log and records(log,"PH CLOCK")==[[125000000,24000000,0]],"clock or app exit")
    (detail,us,low,edges,byte_count,accepted,points,invalid,blind),=records(log,"PH FRAME")
    actual="detail" if detail else "control"
    need(not invalid and mode in (None,actual) and byte_count==77920 and accepted==8,"target geometry or mode")
    cal,=records(log,"PH CAL")
    if not host:
        need(cal[2]==82008 and 0<cal[1]*2/125<cal[0] and cal[3]<=12 and 0<cal[4]<500,
             "80x64 calibration")
        need(0<edges and edges/24<=low*2/125+3<=us+5 and blind<=12,"frame wire timing")
    raw=records(log,"PH B")
    need([row[0] for row in raw]==list(range(FIRST+24)),"missing buckets")
    need(sum(r[1] for r in raw)==us and sum(r[2] for r in raw)==low,"ledger does not close")
    buckets=[measure(u,t) for _,u,t in raw]
    need(all(v["cs_high_us"]>=-12 and v["wall_us"]<=us for v in buckets),"inconsistent per-stage counters")
    rects=[]
    for i,x,y,w,h,fill,preps,attempts,ok,p,s,e in records(log,"PH R"):
        need(ok==1 and attempts>=1 and i==len(rects),"rectangle not accepted once")
        if detail:
            need(preps==1 and fill==int(w==320) and p<=s<=e<=us,"preparation or order")
        rects.append(dict(x=x,y=y,width=w,height=h,fill=fill,attempts=attempts,prep_start=p,submit_start=s,submit_end=e,
                          prepare=buckets[FIRST+i],submit=buckets[FIRST+8+i],queue=buckets[FIRST+16+i]))
    geometry=[(r["x"],r["y"],r["width"],r["height"]) for r in rects]
    need([g for g in geometry if g[2]!=320]==VISIBLE,"seven visible window coordinates")
    # The hidden write can cross the game's display callback. Keep the
    # captured y and order for the actual scheduler-to-scheduler interval.
    black=[g for g in geometry if g[2]==320]
    need(len(black)==1 and black[0][0]==0 and black[0][3]==32 and black[0][1] in range(0,169,32),
         "hidden 320x32 fill")
    waits=[dict(lead_ms=lead,slack_ms=slack,loops=n,**measure(u,t)) for lead,slack,n,u,t in records(log,"PH T")]
    if detail:
        need(points>0 and len(waits)>=2 and waits[-1]["lead_ms"]==0,"timer capture")
    else:
        need(not points and not waits,"unexpected control instrumentation")
    return dict(mode=actual,frame=measure(us,low),edges=edges,points=points,cal_read_256_us=cal[4],
                stages=dict(zip(BASE,buckets[:FIRST])),rects=rects,waits=waits)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs",nargs="+",type=Path)
    parser.add_argument("--rectangles",type=Path)
    args=parser.parse_args()
    rows=[]
    for path in args.logs:
        q=parse(path.read_text())
        print(path.name,q["mode"],q["frame"],"timer",q["waits"])
        if q["mode"]!="detail": continue
        for r in q["rects"]:
            row={"run":path.stem,**{k:v for k,v in r.items() if not isinstance(v,dict)}}
            for task in ("prepare","submit","queue"):
                row.update({task+"_"+k:r[task][k] for k in ("wall_us","cs_low_us","cs_high_us")})
            rows.append(row)
    if rows and args.rectangles:
        with args.rectangles.open("w",newline="") as f:
            writer=csv.DictWriter(f,rows[0].keys(),lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


if __name__=="__main__":
    main()
