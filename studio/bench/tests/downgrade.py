from ..registry import register
from .. import probe

def run(ctx):
    cfg=ctx.get("probe_config") or {};ref=cfg.get("reference")
    measurement=probe.measure(ctx["client"],cfg.get("config") or probe.config())
    comparison=probe.compare(ref,measurement)
    comparison["reference_details"]=cfg.get("reference_source")
    return {"light":"warn" if comparison["status"]=="capability_deviation" else "info",
            "summary_zh":comparison["summary"],"metrics":{"comparison":comparison},
            "evidence":{"measurement":measurement,"reference_id":cfg.get("reference_id")}}
register("downgrade","能力对照探针（实验性）","capability",
         "18道参数化任务各重复2次，共36次调用；参考报告与待测接入使用相同题集。",
         "至少17个有效配对，参考通过率≥80%；下降≥20个百分点且单侧p≤0.01提示偏离，不验证模型身份。",180,True,run)
