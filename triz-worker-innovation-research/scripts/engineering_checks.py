"""Small explicit comparison/unit contracts; does not certify experimental validity."""
import ast
import math


def comparable(candidate, baseline, protocols):
    """An identifier alone cannot make two observations comparable."""
    errors = []
    if baseline.get('target_kind') != 'baseline_system' or baseline.get('route_id') == candidate.get('route_id'):
        errors.append('baseline must be a distinct baseline_system route')
    if baseline.get('baseline_test_id'):
        errors.append('baseline chains/cycles cannot support maturity')
    left = protocols.get(candidate.get('protocol_id'), {})
    right = protocols.get(baseline.get('protocol_id'), {})
    for key in ('scope', 'sampling_plan', 'comparison_basis'):
        if not left.get(key) or left.get(key) != right.get(key):
            errors.append('incomparable protocol ' + key)
    basis = left.get('comparison_basis', {})
    for key in ('object_population', 'metric_definition', 'reference_points', 'instrument_chain'):
        if not isinstance(basis, dict) or not basis.get(key):
            errors.append('comparison_basis missing ' + key)
    a = {m.get('id'): m.get('unit') for m in left.get('metrics', [])}
    b = {m.get('id'): m.get('unit') for m in right.get('metrics', [])}
    if a != b:
        errors.append('incomparable metric IDs/units')
    # Preserve raw conditions separately. These are the declared comparable strata,
    # not a free-text boolean saying "equivalent".
    ca, cb = candidate.get('comparison_conditions'), baseline.get('comparison_conditions')
    if not isinstance(ca, dict) or not ca or not isinstance(cb, dict) or set(ca) != set(cb):
        errors.append('comparison_conditions requires matching nonempty condition keys')
    else:
        tolerances = left.get('condition_tolerances', {})
        if tolerances != right.get('condition_tolerances', {}):
            errors.append('condition tolerances must be predeclared in both protocols')
        for key in ca:
            if ca[key] == cb[key]:
                continue
            tolerance = tolerances.get(key)
            numeric = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
            if not (numeric(tolerance) and tolerance >= 0 and numeric(ca[key]) and numeric(cb[key]) and abs(ca[key] - cb[key]) <= tolerance):
                errors.append('incomparable condition ' + key)
    if not candidate.get('comparison_rationale'):
        errors.append('comparison requires rationale, permitted differences and limitations')
    return errors


# Base dimensions are independent for the limited benefit contracts. SI derived
# units can be extended deliberately, never guessed from unknown unit strings.
UNITS = {
    's': (1, {'time': 1}), 'min': (60, {'time': 1}), 'h': (3600, {'time': 1}),
    'm': (1, {'length': 1}), 'mm': (.001, {'length': 1}),
    'A': (1, {'current': 1}), 'mA': (.001, {'current': 1}),
    'V': (1, {'voltage': 1}), 'kV': (1000, {'voltage': 1}),
    'J': (1, {'energy': 1}), 'kWh': (3600000, {'energy': 1}),
    'CNY': (1, {'currency': 1}), 'count': (1, {'count': 1}),
    'person': (1, {'person': 1}), 'year': (1, {'year': 1}),
}
ALIASES = {'秒': 's', '分钟': 'min', '小时': 'h', '元': 'CNY', '次': 'count', '件': 'count',
           '个': 'count', '端': 'count', '人': 'person', '年': 'year'}


def combine(a, b, sign=1):
    dims = dict(a)
    for key, value in b.items():
        dims[key] = dims.get(key, 0) + sign * value
    return {k: v for k, v in dims.items() if v}


def unit(value):
    if not isinstance(value, str) or len(value) > 160:
        raise NotImplementedError('unit must be a supported explicit expression')
    for source, target in ALIASES.items():
        value = value.replace(source, target)
    def walk(node):
        if isinstance(node, ast.Expression): return walk(node.body)
        if isinstance(node, ast.Name) and node.id in UNITS: return UNITS[node.id]
        if isinstance(node, ast.Constant) and node.value == 1: return 1, {}
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Div)):
            af, ad = walk(node.left); bf, bd = walk(node.right)
            return (af * bf, combine(ad, bd)) if isinstance(node.op, ast.Mult) else (af / bf, combine(ad, bd, -1))
        raise NotImplementedError('unsupported unit expression: ' + value)
    try: return walk(ast.parse(value, mode='eval'))
    except SyntaxError as error: raise NotImplementedError('unsupported unit expression: ' + value) from error


def benefit_with_units(model):
    """Return the result in the declared output unit, including scale conversion."""
    out_factor, out_dimension = unit(model.get('unit'))
    if model['formula_type'] == 'linear_difference_rate':
        inputs, units = model['inputs'], model.get('input_units', {})
        parsed = {key: unit(units.get(key)) for key in ('baseline', 'candidate', 'quantity', 'unit_rate')}
        if parsed['baseline'][1] != parsed['candidate'][1]:
            raise ValueError('baseline/candidate dimension mismatch')
        dimension = combine(combine(parsed['baseline'][1], parsed['quantity'][1]), parsed['unit_rate'][1])
        if dimension != out_dimension:
            raise ValueError('benefit output dimension mismatch')
        return ((inputs['baseline'] * parsed['baseline'][0] - inputs['candidate'] * parsed['candidate'][0])
                * inputs.get('quantity', 1) * parsed['quantity'][0]
                * inputs.get('unit_rate', 1) * parsed['unit_rate'][0] / out_factor)
    if model['formula_type'] == 'net_benefit':
        result = 0
        for key, sign in [('benefits', 1), ('costs', -1)]:
            for item in model['inputs'][key]:
                factor, dimension = unit(item.get('unit'))
                if dimension != out_dimension: raise ValueError('net benefit dimension mismatch')
                result += sign * item['value'] * factor / out_factor
        return result
    raise NotImplementedError('dimensional calculation not implemented')
