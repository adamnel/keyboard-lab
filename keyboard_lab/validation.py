"""Fail closed for unknown automated checks; manual evidence is never inferred."""
import yaml
from .model import ROOT, read_json, parse_code, shape

def validate(layout, requirements=None):
    req = requirements or yaml.safe_load((ROOT / "requirements.yaml").read_text())
    pos = read_json(ROOT / "firmware/positions.json")
    valid_shape = shape(layout)
    results = []
    for r in req["requirements"]:
        check = r["check"]
        if check == "manual":
            state, evidence = "unverified", "Requires user/application evidence; not proven by keymap analysis."
        elif not valid_shape:
            state, evidence = "fail", "Expected eight layers of eight rows by seven columns, containing uint16 keycodes."
        elif check == "geometry":
            cells = [tuple(v["matrix"]) for v in pos.values()]
            ok = len(cells) == len(set(cells)) == 46
            state, evidence = ("pass" if ok else "fail"), "46 unique physical positions; 8x8x7 keymap dimensions."
        elif check == "binding":
            row, col = pos[r["position"]]["matrix"]
            expected = parse_code(r["code"])
            actual = layout[r["layer"]][row][col]
            state, evidence = ("pass" if actual == expected else "fail"), f"Expected {expected:#06x}, got {actual:#06x}."
        elif check == "qwerty":
            ok = True
            for row, left, right in [(0,"QWERT","YUIOP"),(1,"ASDFG","HJKL"),(2,"ZXCVB","NM")]:
                for col, letter in enumerate(left,1):
                    ok &= layout[0][row][col] == parse_code("KC_"+letter)
                for col, letter in zip(range(5,0,-1),right):
                    ok &= layout[0][row+4][col] == parse_code("KC_"+letter)
            state,evidence=("pass" if ok else "fail"),"QWERTY letter matrix checked."
        elif check == "starter_layer_access":
            left = pos["left.thumb.middle"]["matrix"]
            right = pos["right.thumb.middle"]["matrix"]
            ok = layout[0][left[0]][left[1]] == parse_code("TL_LOWR") and layout[0][right[0]][right[1]] == parse_code("TL_UPPR")
            state,evidence=("pass" if ok else "fail"),"Checks starter tri-layer entry bindings only; runtime tri-layer settings are outside snapshot scope."
        else:
            state,evidence="fail",f"No validator for declared check: {check}"
        results.append({"id":r["id"],"kind":r["kind"],"status":state,"evidence":evidence})
    return results

def assert_valid(layout):
    report=validate(layout)
    failed=[r["id"] for r in report if r["status"]=="fail"]
    if failed:
        raise ValueError("Requirements failed: " + ", ".join(failed))
    return report
