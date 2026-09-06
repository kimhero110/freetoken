"""Deterministic text API estimates. No I/O, credentials, floats or implicit FX."""
from decimal import Decimal, localcontext, ROUND_HALF_UP
import hashlib
import json
import re

VERSION = '1.1.0'
DIMENSIONS = ('input', 'cached', 'output')

def number(value, integer=False):
    pattern = r'\d{1,15}' if integer else r'\d{1,15}(\.\d{1,12})?'
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValueError('请输入非负整数用量或最多12位小数的金额')
    return Decimal(value)

def money(value):
    if value is None:
        return None
    return format(value, 'f')

def estimate(workload, offer, credit='0', fx=None):
    with localcontext() as ctx:
        ctx.prec = 72
        return _estimate(workload, offer, credit, fx)

def _estimate(workload, offer, credit, fx):
    if not isinstance(workload, dict) or not isinstance(offer, dict):
        raise ValueError('用量与报价必须是对象')
    workload = {k:workload.get(k) for k in ('input','cached','output','peak_rpm','peak_tpm','context','max_output')}
    if offer.get('currency') not in ('USD', 'CNY') or not offer.get('model'):
        raise ValueError('报价必须指定模型及 USD/CNY 币种')
    if offer.get('rule', 'linear_tokens') != 'linear_tokens':
        raise ValueError('当前版本尚不支持该计费规则，请使用明确的文本按量报价')
    quantities = {}
    for key in DIMENSIONS:
        value = workload.get(key)
        quantities[key] = None if value is None else number(value, True)
    i, c, o = (quantities[k] for k in DIMENSIONS)
    if i is not None and c is not None and c > i:
        raise ValueError('缓存命中量不能大于总输入量')
    counts = (None if i is None or c is None else i-c, c, o)
    missing, lines, subtotal = [], [], Decimal(0)
    rates = offer.get('rates', {})
    pack=offer.get('credit_pack')
    factor=Decimal(1)
    if pack:
        paid=number(pack.get('paid'));units=number(pack.get('units'))
        if units<=0:raise ValueError('到账计费单位必须大于0')
        factor=paid/units

    for dim, count in zip(DIMENSIONS, counts):
        raw = rates.get(dim)
        rate = None if raw is None else number(raw)*factor
        cost = Decimal(0) if count == 0 else None if count is None or rate is None else count*rate/Decimal(1000000)
        if cost is None:
            missing.append(dim)
        else:
            subtotal += cost
        lines.append({'dimension': dim, 'quantity': money(count), 'rate_per_million': money(rate), 'cost': money(cost)})
    allowance = number(credit)
    gross = None if missing else subtotal
    applied = None if gross is None else min(gross, allowance)
    total = None if gross is None else gross-applied
    eligibility = {}
    limits = offer.get('limits', {})
    for key in ('peak_rpm', 'peak_tpm', 'context', 'max_output'):
        requested = workload.get(key)
        limit = limits.get(key)
        if requested is None or requested == '':
            eligibility[key] = 'unknown'
        elif limit is None:
            number(requested, True)
            eligibility[key] = 'unknown'
        else:
            eligibility[key] = 'eligible' if number(requested, True) <= number(str(limit), True) else 'ineligible'
    applicable = 'ineligible' if 'ineligible' in eligibility.values() else 'unknown' if 'unknown' in eligibility.values() else 'eligible'
    result = {'schema_version': 1, 'engine_version': VERSION, 'offer': offer, 'workload': workload,
              'currency': offer['currency'], 'lines': lines, 'known_subtotal': money(subtotal),
              'gross': money(gross), 'credit_applied': money(applied), 'credit_requested': credit,
              'total': money(total), 'missing_dimensions': missing,
              'calculation_status': 'partial' if missing else 'complete',
              'eligibility_status': applicable, 'conditions': eligibility,
              'scope': '文本 Token 按量估算；不含税费、工具、搜索、图片及套餐费用。余额需确认适用于该模型与本期。',
              'rounding': '高精度分项求和；界面显示舍入不代表厂商结算规则'}
    if fx:
        if fx.get('to') not in ('USD', 'CNY') or fx['to'] == offer['currency']:
            raise ValueError('汇率目标币种必须与原币种不同')
        rate = number(fx.get('rate'))
        if rate <= 0 or not fx.get('as_of'):
            raise ValueError('汇率必须为正数，并提供快照日期')
        result['fx'] = dict(fx)
        result['converted_total'] = money(None if total is None else total*rate)
    canonical = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    result['analysis_id'] = hashlib.sha256(canonical.encode()).hexdigest()[:24]
    return result

def compare(workload, offers):
    if not 1 <= len(offers) <= 20:
        raise ValueError('每次可比较1至20个报价')
    results = [estimate(workload, offer) for offer in offers]
    groups = {}
    for r in results:
        key = (r['offer']['model'], r['currency'])
        groups.setdefault(key, []).append(r)
    output = []
    for (model, currency), rows in groups.items():
        complete = [r for r in rows if r['total'] is not None and r['eligibility_status'] != 'ineligible']
        complete.sort(key=lambda r: Decimal(r['total']))
        remainder = [r for r in rows if r not in complete]
        output.append({'model': model, 'currency': currency, 'results': complete+remainder,
                       'comparison_status': 'conditional' if any(r['eligibility_status'] != 'eligible' for r in rows) else 'comparable',
                       'note': '同模型、同币种、同用量的成本顺序；适用条件未知时不构成可用性推荐。不同组不排名。'})
    return output

def observation_cost(observations, offer):
    """Sum each call independently; never infer unobserved billing as zero."""
    with localcontext() as ctx:
        ctx.prec = 72
        calls = [o for o in observations if o['operation'] == 'chat']
        subtotal, complete, rows = Decimal(0), 0, []
        for call in calls:
            analysis = estimate(call['usage'], offer)
            subtotal += Decimal(analysis['known_subtotal'])
            complete += analysis['total'] is not None
            rows.append({'call_id': call['call_id'], 'test_id': call['test_id'], 'status': call['status'],
                         'total': analysis['total'], 'missing_dimensions': analysis['missing_dimensions']})
        return {'engine_version': VERSION, 'offer': offer, 'currency': offer['currency'],
                'known_subtotal': money(subtotal), 'total': money(subtotal) if complete == len(calls) else None,
                'calls': rows, 'covered_calls': complete, 'total_calls': len(calls),
                'label': '本次测试按报价估算费用，不是实际扣费；失败或超时请求仍可能收费。'}
