use serde_json::{Value as J, json};
use spween::*;
use std::{
    collections::BTreeMap,
    io::{self, BufRead, Write},
};
const PIN: &str = "95980f7d1e109138496849a444f28c4b9076a4e2";
fn span(s: &Span) -> J {
    json!([s.start, s.end])
}
fn value(v: &Value) -> J {
    match v {
        Value::Null => json!(["null"]),
        Value::Bool(b) => json!(["bool", b]),
        Value::Int(i) => json!(["int", i.to_string()]),
        Value::Float(f) => json!(["float", format!("{:016x}", f.to_bits())]),
        Value::String(s) => json!(["string", s.as_str()]),
    }
}
fn input_value(j: &J) -> Result<Value, String> {
    let a = j.as_array().ok_or("value must be tagged array")?;
    let tag = a.first().and_then(J::as_str).ok_or("missing value tag")?;
    if tag == "null" && a.len() == 1 {
        return Ok(Value::Null);
    }
    if a.len() != 2 {
        return Err("value requires exactly tag and payload".into());
    }
    Ok(match tag {
        "bool" => Value::Bool(a[1].as_bool().ok_or("bool payload")?),
        "string" => Value::from(a[1].as_str().ok_or("string payload")?),
        "int" => {
            let s = a[1].as_str().ok_or("int decimal string")?;
            let n = s.parse::<i64>().map_err(|_| "int outside i64")?;
            if n.to_string() != s {
                return Err("noncanonical int".into());
            }
            Value::Int(n)
        }
        "float" => {
            let s = a[1].as_str().ok_or("float bits string")?;
            if s.len() != 16
                || !s
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
            {
                return Err("float requires 16 lowercase hex bits".into());
            }
            Value::Float(f64::from_bits(
                u64::from_str_radix(s, 16).map_err(|_| "float bits")?,
            ))
        }
        _ => return Err(format!("unknown value tag {tag}")),
    })
}
fn clause(c: &ConditionClause) -> J {
    match c {
        ConditionClause::Has(h) => {
            json!({"kind":"has","category":h.category.as_str(),"key":h.key.as_str(),"span":span(&h.span)})
        }
        ConditionClause::Compare(c) => {
            json!({"kind":"compare","var":c.var.as_str(),"op":match c.op { CompareOp::Ge=>"ge",CompareOp::Le=>"le",CompareOp::Gt=>"gt",CompareOp::Lt=>"lt",CompareOp::Eq=>"eq",CompareOp::Ne=>"ne" },"value":value(&c.value),"span":span(&c.span)})
        }
        ConditionClause::Not(c) => json!({"kind":"not","clause":clause(c)}),
    }
}
fn expr(e: &ConditionExpr) -> J {
    match e {
        ConditionExpr::Atom(c) => json!(["atom", clause(c)]),
        ConditionExpr::And(a, b) => json!(["and", expr(a), expr(b)]),
        ConditionExpr::Or(a, b) => json!(["or", expr(a), expr(b)]),
    }
}
fn condition(c: &Option<Condition>) -> J {
    c.as_ref()
        .map(|c| json!({"expr":expr(&c.expr),"span":span(&c.span)}))
        .unwrap_or(J::Null)
}
fn effect(e: &Effect) -> J {
    match e {
        Effect::Set(s) => {
            json!({"kind":"set","var":s.var.as_str(),"value":value(&s.value),"span":span(&s.span)})
        }
        Effect::Modify(m) => {
            json!({"kind":"modify","var":m.var.as_str(),"delta":m.delta.to_string(),"span":span(&m.span)})
        }
        Effect::Call(c) => {
            json!({"kind":"call","name":c.name.as_str(),"args":c.args.iter().map(value).collect::<Vec<_>>(),"span":span(&c.span)})
        }
    }
}
fn scene(s: &Scene) -> J {
    let m = &s.meta;
    json!({"span":span(&s.span),"meta":{
        "id":m.id.as_str(),"title":m.title.as_str(),"tags":m.tags.iter().map(|s|s.as_str()).collect::<Vec<_>>(),
        "weight":m.weight,"cooldown":m.cooldown,"requires":condition(&m.requires),
        "custom":m.custom.iter().map(|(k,v)|json!([k.as_str(),value(v)])).collect::<Vec<_>>(),"span":span(&m.span)
    },"passages":s.passages.iter().map(|p|json!({"name":p.name.as_str(),"span":span(&p.span),"content":p.content.iter().map(|c|match c {
        PassageContent::Prose(p)=>json!({"kind":"prose","text":p.text.as_str(),"span":span(&p.span)}),
        PassageContent::Effect(e)=>json!({"kind":"effect","effect":effect(e)}),
        PassageContent::Choice(c)=>json!({"kind":"choice","text":c.text.as_str(),"condition":condition(&c.condition),"effects":c.effects.iter().map(effect).collect::<Vec<_>>(),"target":c.target.as_ref().map(|n|json!({"target":n.target.as_str(),"is_end":n.is_end,"span":span(&n.span)})),"span":span(&c.span)}),
    }).collect::<Vec<_>>()})).collect::<Vec<_>>()})
}
#[derive(Default)]
struct Handler {
    vars: BTreeMap<String, Value>,
    has: BTreeMap<String, Vec<String>>,
    calls: Vec<J>,
}
impl EffectHandler for Handler {
    fn get_var(&self, n: &str) -> Value {
        self.vars.get(n).cloned().unwrap_or(Value::Null)
    }
    fn set_var(&mut self, n: &str, v: Value) {
        self.vars.insert(n.into(), v);
    }
    fn has(&self, c: &str, k: &str) -> bool {
        self.has
            .get(c)
            .map(|keys| keys.iter().any(|x| x == k))
            .unwrap_or(false)
    }
    fn call(&mut self, n: &str, a: &[Value]) -> Result<(), String> {
        self.calls
            .push(json!({"name":n,"args":a.iter().map(value).collect::<Vec<_>>() }));
        Ok(())
    }
}
fn handler(j: Option<&J>) -> Result<Handler, String> {
    let mut h = Handler::default();
    if let Some(j) = j {
        fields(j, &["vars", "has"])?;
        if let Some(vars) = j.get("vars") {
            for (k, v) in vars.as_object().ok_or("vars object")? {
                h.vars.insert(k.clone(), input_value(v)?);
            }
        }
        if let Some(has) = j.get("has") {
            for (k, v) in has.as_object().ok_or("has object")? {
                h.has.insert(
                    k.clone(),
                    v.as_array()
                        .ok_or("has array")?
                        .iter()
                        .map(|s| s.as_str().map(str::to_owned).ok_or("has string".into()))
                        .collect::<Result<_, String>>()?,
                );
            }
        }
    }
    Ok(h)
}
fn snapshot(r: &Runtime<'_, Handler>) -> J {
    json!({
        "state":match r.state() { RuntimeState::Ended=>json!({"kind":"ended"}),RuntimeState::Running(i)=>json!({"kind":"running","index":i,"passage":r.current_passage().map(|p|p.name.as_str())}) },
        "vars":r.handler().vars.iter().map(|(k,v)|(k.clone(),value(v))).collect::<serde_json::Map<String,J>>(),
        "has":r.handler().has,"calls":r.handler().calls,"prose":r.current_prose(),"requirements":r.check_scene_requirements(),
        "choices":r.current_choices().iter().map(|c|json!({"index":c.index,"text":c.text.as_str(),"available":c.available})).collect::<Vec<_>>()
    })
}
fn fields(j: &J, allowed: &[&str]) -> Result<(), String> {
    for k in j.as_object().ok_or("expected object")?.keys() {
        if !allowed.contains(&k.as_str()) {
            return Err(format!("unknown field {k}"));
        }
    }
    Ok(())
}
fn run(j: &J) -> Result<J, String> {
    fields(j, &["op", "source", "filename", "state", "actions"])?;
    let op = j.get("op").and_then(J::as_str).ok_or("op required")?;
    if op != "parse" && op != "replay" {
        return Err("op must be parse or replay".into());
    }
    if op == "parse" && (j.get("state").is_some() || j.get("actions").is_some()) {
        return Err("state/actions are replay-only".into());
    }
    let source = j
        .get("source")
        .and_then(J::as_str)
        .ok_or("source string required")?;
    let filename = match j.get("filename") {
        None => "input.scene",
        Some(v) => v.as_str().ok_or("filename string")?,
    };
    let s = match parse(source, filename) {
        Ok(s) => s,
        Err(e) => {
            return Ok(
                json!({"ok":false,"stage":"parse","error":e.to_string(),"span":span(&e.span()),"upstream":PIN}),
            );
        }
    };
    if op == "parse" {
        return Ok(json!({"ok":true,"upstream":PIN,"source":source,"ast":scene(&s)}));
    }
    let mut r = Runtime::new(&s, handler(j.get("state"))?).map_err(|e| e.to_string())?;
    let mut trace = vec![json!({"action":null,"ok":true,"snapshot":snapshot(&r)})];
    let empty = vec![];
    let actions = match j.get("actions") {
        None => &empty,
        Some(v) => v.as_array().ok_or("actions array")?,
    };
    for a in actions {
        fields(a, &["choose", "jump"])?;
        if a.as_object().unwrap().len() != 1 {
            return Err("action requires one of choose/jump".into());
        }
        let result = if let Some(v) = a.get("choose") {
            r.select_choice(
                usize::try_from(v.as_u64().ok_or("choose unsigned integer")?)
                    .map_err(|_| "choose index overflow")?,
            )
        } else {
            r.jump_to(a["jump"].as_str().ok_or("jump string")?)
        };
        trace.push(json!({"action":a,"ok":result.is_ok(),"error":result.err().map(|e|e.to_string()),"snapshot":snapshot(&r)}));
    }
    Ok(json!({"ok":true,"upstream":PIN,"trace":trace}))
}
fn main() {
    // Upstream may panic on arithmetic overflow or malformed parser edge cases.
    // Keep a line-oriented oracle alive, but never reinterpret a panic as semantics.
    std::panic::set_hook(Box::new(|_| {}));
    let stdin = io::stdin();
    let mut stdout = io::BufWriter::new(io::stdout().lock());
    for line in stdin.lock().lines() {
        let line = line.map_err(|e| e.to_string());
        let output = std::panic::catch_unwind(|| -> Result<J, String> {
            let line = line?;
            if line.len() > 2 * 1024 * 1024 {
                return Err("request exceeds 2 MiB".into());
            }
            run(&serde_json::from_str::<J>(&line).map_err(|e| e.to_string())?)
        });
        let output = match output {
            Ok(Ok(v)) => v,
            Ok(Err(e)) => json!({"ok":false,"stage":"bridge","error":e,"upstream":PIN}),
            Err(_) => {
                json!({"ok":false,"stage":"upstream-panic","error":"upstream parser/runtime panicked; no semantic result","upstream":PIN})
            }
        };
        if writeln!(stdout, "{output}")
            .and_then(|_| stdout.flush())
            .is_err()
        {
            break;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn source(body: &str) -> String {
        format!("---\nid: bridge\ntitle: Bridge\nweight: 1\ncooldown: 0\n---\n{body}\n")
    }
    fn replay(body: &str, state: J, actions: J) -> J {
        run(&json!({"op":"replay","source":source(body),"state":state,"actions":actions})).unwrap()
    }
    #[test]
    fn tagged_values_preserve_distinctions_and_bits() {
        for v in [
            Value::Null,
            Value::Bool(true),
            Value::Int(i64::MIN),
            Value::Int(i64::MAX),
            Value::Float(-0.0),
            Value::Float(f64::INFINITY),
            Value::Float(f64::from_bits(0x7ff8000000000001)),
            Value::from("🜉✾"),
        ] {
            let wire = value(&v);
            assert_eq!(value(&input_value(&wire).unwrap()), wire);
        }
        for bad in [
            json!(["int", "01"]),
            json!(["int", "-0"]),
            json!(["int", "9223372036854775808"]),
            json!(["float", "0"]),
            json!(["null", 0]),
        ] {
            assert!(input_value(&bad).is_err());
        }
    }
    #[test]
    fn full_ast_retains_source_spans_and_types() {
        let src = "---\nid: x\ntitle: X\ntags: [one, two]\nweight: 2\ncooldown: 3\ncustom: 1.5\n---\n=== intro\nUnicode 🜉✾.\n~ x = -3\n* [Go] { inventory.key && x < 1 || !flag }\n  ~ x += 2\n  ~ notify \"hello\"\n  -> END\n";
        let parsed = run(&json!({"op":"parse","source":src})).unwrap();
        assert_eq!(parsed["ok"], true);
        assert_eq!(parsed["source"], src);
        let ast = &parsed["ast"];
        assert_eq!(ast["meta"]["tags"], json!(["one", "two"]));
        assert_eq!(
            ast["meta"]["custom"][0],
            json!(["custom", ["float", "3ff8000000000000"]])
        );
        let content = ast["passages"][0]["content"].as_array().unwrap();
        assert!(content.iter().any(|x| x["kind"] == "prose"));
        assert!(
            content
                .iter()
                .any(|x| x["effect"]["value"] == json!(["int", "-3"]))
        );
        let choice = content.iter().find(|x| x["kind"] == "choice").unwrap();
        assert_eq!(choice["effects"][0]["delta"], "2");
        assert_eq!(choice["effects"][1]["kind"], "call");
        assert_eq!(choice["target"]["is_end"], true);
        assert!(choice["condition"]["expr"].is_array());
        fn spans(j: &J, len: usize) {
            match j {
                J::Object(o) => {
                    for (k, v) in o {
                        if k == "span" {
                            let a = v.as_array().unwrap();
                            assert!(a[0].as_u64().unwrap() <= a[1].as_u64().unwrap());
                            assert!(a[1].as_u64().unwrap() <= len as u64);
                        } else {
                            spans(v, len)
                        }
                    }
                }
                J::Array(a) => {
                    for v in a {
                        spans(v, len)
                    }
                }
                _ => (),
            }
        }
        spans(ast, src.len());
    }
    #[test]
    fn actual_runtime_entry_effects_once_and_ordered_calls() {
        let r = replay(
            "=== a\n~ gold = 100\n* [Spend]\n  ~ gold -= 40\n  ~ notify \"spent\"\n  -> b\n=== b\n* [Back]\n  -> a",
            json!({}),
            json!([{"choose":0},{"choose":0}]),
        );
        assert_eq!(
            r["trace"][0]["snapshot"]["vars"]["gold"],
            json!(["int", "100"])
        );
        assert_eq!(
            r["trace"][2]["snapshot"]["vars"]["gold"],
            json!(["int", "60"])
        );
        assert_eq!(
            r["trace"][2]["snapshot"]["calls"],
            json!([{"name":"notify","args":[["string","spent"]]}])
        );
    }
    #[test]
    fn actual_runtime_coercion_and_non_numeric_modify() {
        let r = replay(
            "=== a\n~ text += 5\n~ missing -= 2\n* [Bool equals one] { flag == 1 }\n  -> END\n* [Has] { inventory.key }\n  -> END\n* [Unavailable] { missing > 0 }\n  -> END",
            json!({"vars":{"text":["string","same"],"flag":["bool",true]},"has":{"inventory":["key"]}}),
            json!([{"choose":2}]),
        );
        let s = &r["trace"][0]["snapshot"];
        assert_eq!(s["vars"]["text"], json!(["string", "same"]));
        assert_eq!(s["vars"]["missing"], json!(["int", "-2"]));
        assert_eq!(s["choices"][0]["available"], true);
        assert_eq!(s["choices"][1]["available"], true);
        assert_eq!(r["trace"][1]["ok"], false);
        assert_eq!(r["trace"][1]["snapshot"], *s);
    }
    #[test]
    fn upstream_failure_is_not_atomic() {
        let r = replay(
            "=== a\n* [Bad target]\n  ~ value = 4\n  -> absent",
            json!({}),
            json!([{"choose":0}]),
        );
        assert_eq!(r["trace"][1]["ok"], false);
        assert_eq!(
            r["trace"][1]["snapshot"]["vars"]["value"],
            json!(["int", "4"])
        );
    }
    #[test]
    fn malformed_requests_refuse() {
        for j in [
            json!({"op":"guess","source":""}),
            json!({"op":"parse","source":"","state":{}}),
            json!({"op":"parse","source":"","extra":1}),
        ] {
            assert!(run(&j).is_err());
        }
    }
}
