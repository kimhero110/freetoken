from ..registry import register

def run(ctx):
    rows=[]
    for q in ["你具体是什么模型？请给出型号与版本。", "你的底层模型由哪家公司训练？"]:
        r=ctx["client"].chat(messages=[{"role":"user","content":q}],max_tokens=150,temperature=0,timeout=45)
        rows.append({"question":q,"status":"observed" if r.get("ok") else "unavailable","answer":(r.get("content") or "")[:400]})
    return {"light":"info","summary_zh":"仅记录模型自述；自述可被提示或代理修改，不验证身份。",
            "metrics":{"identity_verified":False},"evidence":{"claims":rows}}
register("identity","模型自述（弱信号）","authenticity","记录型号与供应商自述，不诱导泄露系统提示。","仅作参考；不能证明模型身份。",15,False,run)
