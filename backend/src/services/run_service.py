import csv,io
import numpy as np
from redis import Redis
from fastapi import HTTPException
from ..models import SpectralLibrary,Endmember,MixtureSample,UnmixRun,ReplicationNote
from ..config.settings import REDIS_URL
from ..utils.serialize import record
from .unmix_algorithm import matrix_diagnostics
from .band_selection import resolve_band_mask
from .audit_service import log
queue=Redis.from_url(REDIS_URL,decode_responses=True)
def list_runs(db):return [record(r) for r in db.query(UnmixRun).order_by(UnmixRun.id.desc())]
def get_run(db,rid):
    row=db.get(UnmixRun,rid)
    if not row:raise HTTPException(404,"解混运行不存在")
    return row

def create_snapshot(db,library,sample_ids):
    members=db.query(Endmember).filter_by(library_id=library.id).order_by(Endmember.code).all()
    samples=db.query(MixtureSample).filter(MixtureSample.id.in_(sample_ids),MixtureSample.library_id==library.id).order_by(MixtureSample.code).all()
    if len(samples)!=len(sample_ids):raise HTTPException(422,"样本重复、不存在或不属于所选光谱库")
    return {"library":record(library),"endmembers":[record(e) for e in members],"samples":[record(s) for s in samples]}
def create_run(db,data,user):
    library=db.get(SpectralLibrary,data.library_id)
    if not library:raise HTTPException(404,"光谱库不存在")
    if len(set(data.sample_ids))!=len(data.sample_ids) or len(data.sample_ids)*data.repeats>480:raise HTTPException(422,"样本不可重复，样本数×重复数不得超过480")
    snapshot=create_snapshot(db,library,data.sample_ids)
    try:
        # 先按波长冻结排除规则，再在保留波段上做可辨识性预检；不可辨识直接拒绝入队。
        retained_idx,_,exclusions=resolve_band_mask(library.wavelengths,data.band_exclusions)
        A_full=np.array([e['spectrum'] for e in snapshot['endmembers']]).T
        _,d=matrix_diagnostics(A_full[retained_idx,:])
        if not d['supported']:raise ValueError(d['reason'])
    except ValueError as e:raise HTTPException(422,str(e))
    row=UnmixRun(**data.model_dump(),input_snapshot=snapshot,owner=user.name)
    row.band_exclusions=exclusions
    db.add(row);db.flush();log(db,user.email,"unmix.enqueue",row.id);db.commit()
    try:queue.rpush("spectral:jobs",row.id)
    except Exception:
        row.status="failed";row.error="队列不可用，请重提";db.commit();raise HTTPException(503,row.error)
    return record(row)
def export_run(db,rid):
    row=get_run(db,rid)
    if row.status!="completed" or not db.query(ReplicationNote).filter_by(run_id=rid,status="approved").first():raise HTTPException(403,"仅获批完成研究可导出")
    exclusions=row.band_exclusions or []
    out=io.StringIO();w=csv.writer(out)
    base_head=['sample','endmember','weight','conditional_q025','conditional_q975','rss','rmse','noise_sigma','repeats','root_seed','input_hash']
    if exclusions:
        retained=";".join(str(x) for x in row.result['retained_wavelengths'])
        excluded=";".join(f"{item['wavelength']:g}nm:{item['reason']}" for item in exclusions)
        w.writerow(base_head+['retained_wavelengths_nm','excluded_wavelengths_nm_reason'])
    else:
        # 未排除任何波段的研究保持旧列序，兼容历史研究与既有阅读者流程。
        w.writerow(base_head)
    for s in row.result['samples']:
        for i,e in enumerate(row.result['endmembers']):
            line=[s['code'],e['code'],s['point_fit']['weights'][i],s['lower'][i],s['upper'][i],s['point_fit']['rss'],s['point_fit']['rmse'],row.noise_sigma,row.repeats,row.seed,row.result['input_hash']]
            if exclusions:line+=[retained,excluded]
            w.writerow(line)
    return out.getvalue()
