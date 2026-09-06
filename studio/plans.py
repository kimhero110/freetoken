"""User-entered subscription comparison; quota percentages are not currency."""
from decimal import localcontext
from cost_core import number,money

def compare(data):
    plans=data.get("plans",[])
    if not isinstance(plans,list) or not 1<=len(plans)<=20:raise ValueError("请加入1至20个套餐")
    out=[]
    with localcontext() as ctx:
        ctx.prec=72
        for p in plans:
            name=str(p.get("name","")).strip()[:100];currency=p.get("currency")
            if not name or currency not in ("USD","CNY"):raise ValueError("请填写套餐名称与币种")
            amount=number(p.get("amount"));months=number(p.get("months"),True)
            if not 1<=months<=36:raise ValueError("付费周期为1至36个月")
            fit=p.get("fit","unknown")
            if fit not in ("yes","no","unknown"):raise ValueError("适用条件无效")
            out.append({"name":name,"currency":currency,"upfront":money(amount),"months":money(months),
                        "monthly_equivalent":money(amount/months),"fit":fit,
                        "limits":str(p.get("limits", ""))[:600],"source":str(p.get("source", "用户自填"))[:500]})
    return {"plans":out,"note":"月均仅为付费周期摊销，不代表支持按月付款。适用性由你确认；未将额度百分比换算为Token或金额。"}
