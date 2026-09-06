import json
from pathlib import Path
from datetime import datetime,timezone,timedelta
from cost_core import number

def pricebook():
    book=json.loads((Path(__file__).parent/'pricebook.json').read_text(encoding='utf-8'))
    offers=[]
    for r in book['records']:
        for period in ('peak','offpeak'):
            for v in r[period].values():
                if v is not None:number(v)
            offers.append({'id':f"{r['platform']}:{r['model']}:{period}",'platform':r['platform'],
                           'model':r['model'],'revision':r['revision'],'currency':r['currency'],'rates':r[period],
                           'period':period,'source':r['source'],'checked_at':r['checked_at'],
                           'evidence':r['evidence'],'pricebook_version':book['version'],'rule':'linear_tokens',
                           'assumption':'全部用量适用所选时段；跨时段需分别计算。高峰为周一至周五北京时间09–12、14–18。'})
    return {'version':book['version'],'offers':offers}

def select(data,model=None):
    if data.get('offer_id'):
        matches=[r for r in pricebook()['offers'] if r['id']==data['offer_id']]
        if not matches:raise ValueError('报价不存在，请重新选择或填写自有报价')
        offer=matches[0]
    else:
        custom=data.get('offer') or {}
        if custom.get('rule', 'linear_tokens') != 'linear_tokens':
            raise ValueError('当前仅支持明确的文本按量报价，套餐等规则尚不支持')
        offer={k:custom.get(k) for k in ('model','currency','rates','credit_pack','label')}
        offer.update(id=str(custom.get('label') or '自填接入')[:100],evidence='user_entered',rule='linear_tokens')
    if model and offer.get('model') != model:
        raise ValueError('报价模型与待测模型不一致；请填写该接入点的准确报价')
    return offer
